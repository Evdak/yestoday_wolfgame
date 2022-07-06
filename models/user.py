import asyncio
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Any

from pywebio import run_async
from pywebio.output import output
from pywebio.session import get_current_session
from pywebio.session.coroutinebased import TaskHandle

from enums import Role, PlayerStatus, LogCtrl, WitchRule, GuardRule, GameStage
from models.system import Config, Global
from stub import OutputHandler
from . import logger

if TYPE_CHECKING:
    from .room import Room


def player_action(func):
    """
    Player operation waits to unlock logic decorator

    1. Only used for game character operations under the User class
    2. When the decorated function returns a string, it will return an error message to the current user and continue to lock
    3. When None / True is returned, the game stage will be unlocked
    """

    def wrapper(self: 'User', *args, **kwargs):
        if self.room is None or self.room.waiting is not True:
            return
        if not self.should_act():
            return

        rv = func(self, *args, **kwargs)
        if rv in [None, True]:
            self.room.waiting = False
            self.room.enter_null_stage()
        if isinstance(rv, str):
            self.send_msg(text=rv)

        return rv

    return wrapper


@dataclass
class User:
    nick: str
    # Session
    main_task_id: Any  # Main Task thread id
    input_blocking: bool

    # Game
    room: Optional['Room']  # The room
    role: Optional[Role]  # role
    skill: dict  # character skill
    status: Optional[PlayerStatus]  # Player status

    game_msg: OutputHandler  # Game log UI Handler
    game_msg_syncer: Optional[TaskHandle]  # Game log synchronization thread

    def __str__(self):
        return self.nick

    __repr__ = __str__

    # Room
    def send_msg(self, text):
        """Send a room message visible only to this user"""
        if self.room:
            self.room.send_msg(text, nick=self.nick)
        else:
            logger.warning(
                'User.send_msg() was called when the player did not enter the room state')

    async def _game_msg_syncer(self):
        """
        Sync self.game_msg and self.room.log

        Managed by Room and runs on the main Task thread of the user session
        """
        last_idx = len(self.room.log)
        while True:
            for msg in self.room.log[last_idx:]:
                if msg[0] == self.nick:
                    self.game_msg.append(f'👂:{msg[1]}')
                elif msg[0] == Config.SYS_NICK:
                    self.game_msg.append(f'📢:{msg[1]}')
                elif msg[0] is None:
                    if msg[1] == LogCtrl.RemoveInput:
                        # Workaround, see https://github.com/wang0618/PyWebIO/issues/32
                        if self.input_blocking:
                            get_current_session().send_client_event({
                                'event': 'from_cancel',
                                'task_id': self.main_task_id,
                                'data': None
                            })

            # clean up records
            if len(self.room.log) > 50000:
                self.room.log = self.room.log[len(self.room.log) // 2:]
            last_idx = len(self.room.log)

            await asyncio.sleep(0.2)

    def start_syncer(self):
        """Start game log synchronization logic, managed by Room"""
        if self.game_msg_syncer is not None:
            raise AssertionError
        self.game_msg_syncer = run_async(self._game_msg_syncer())

    def stop_syncer(self):
        """End game log synchronization logic, managed by Room"""
        if self.game_msg_syncer is None or self.game_msg_syncer.closed():
            raise AssertionError
        self.game_msg_syncer.close()
        self.game_msg_syncer = None

    # player state
    def should_act(self):
        """Currently in the stage of the player's operation"""
        stage_map = {
            GameStage.Day: [],
            GameStage.GUARD: [Role.GUARD],
            GameStage.WITCH: [Role.WITCH],
            GameStage.HUNTER: [Role.HUNTER],
            GameStage.DETECTIVE: [Role.DETECTIVE],
            GameStage.WOLF: [Role.WOLF, Role.WOLF_KING],
        }
        return self.role in stage_map.get(self.room.stage, []) and self.status != PlayerStatus.DEAD

    def witch_has_heal(self):
        """The witch holds the antidote"""
        return self.skill.get('heal') is True

    def witch_has_poison(self):
        """The witch holds poison."""
        return self.skill.get('poison') is True
    # player action

    @player_action
    def skip(self):
        pass

    @player_action
    def wolf_kill_player(self, nick):
        self.room.players[nick].status = PlayerStatus.PENDING_DEAD

    @player_action
    def detective_identify_player(self, nick):
        self.send_msg(
            f"Player {nick}'s identity is {self.room.players[nick].role}")

    @player_action
    def witch_kill_player(self, nick):
        if not self.witch_has_poison():
            return 'No more poison'
        self.room.players[nick].status = PlayerStatus.PENDING_POISON

    @player_action
    def witch_heal_player(self, nick):
        if self.room.witch_rule == WitchRule.NO_SELF_RESCUE:
            if nick == self.nick:
                return "can't save myself"
        if self.room.witch_rule == WitchRule.SELF_RESCUE_FIRST_NIGHT_ONLY:
            if nick == self.nick and self.room.round != 1:
                return 'Only the first night can save yourself'

        if not self.witch_has_heal():
            return 'There is no antidote'
        self.room.players[nick].status = PlayerStatus.PENDING_HEAL

    @player_action
    def guard_protect_player(self, nick):
        if self.skill['last_protect'] == nick:
            return 'Do not guard the same player for two nights'

        if self.room.players[nick].status == PlayerStatus.PENDING_HEAL and \
                self.room.guard_rule == GuardRule.MED_CONFLICT:
            # Conflict with the same guard and the same salvation
            self.room.players[nick].status = PlayerStatus.PENDING_DEAD
            return

        if self.room.players[nick].status == PlayerStatus.PENDING_POISON:
            # Guards cannot defend against witch poison
            return

        self.room.players[nick].status = PlayerStatus.PENDING_GUARD

    @player_action
    def hunter_gun_status(self):
        self.send_msg(
            f'Your firing status is...'
            f"""{"Can shoot" if self.status != PlayerStatus.PENDING_POISON else "Can't shoot"}"""
        )

    # Log in
    @ classmethod
    def validate_nick(cls, nick) -> Optional[str]:
        if nick in Global.users or Config.SYS_NICK in nick:
            return 'nickname already in use'

    @ classmethod
    def alloc(cls, nick, init_task_id) -> 'User':
        if nick in Global.users:
            raise ValueError
        Global.users[nick] = cls(
            nick=nick,
            main_task_id=init_task_id,
            input_blocking=False,
            room=None,
            role=None,
            skill=dict(),
            status=None,
            game_msg=output(),
            game_msg_syncer=None
        )
        logger.info(f'user "{nick}" logged in')
        return Global.users[nick]

    @ classmethod
    def free(cls, user: 'User'):
        # unregister
        Global.users.pop(user.nick)
        # remove user from room
        if user.room:
            user.room.remove_player(user)
        logger.info(f'User "{user.nick}" logged out')
