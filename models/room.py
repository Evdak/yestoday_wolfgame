import asyncio
import random
from collections import Counter
from copy import copy
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, Union

from pywebio import run_async
from pywebio.session.coroutinebased import TaskHandle

from enums import Role, WitchRule, GuardRule, GameStage, LogCtrl, PlayerStatus
from models.system import Global, Config
from models.user import User
from utils import say
from . import logger


@dataclass
class Room:
    # This id should be written by the Global manager when registering the room to the room registry
    id: Optional[int]
    # Static settings
    roles: List[Role]
    witch_rule: WitchRule
    guard_rule: GuardRule

    # Dynamic
    started: bool  # Game start state
    # Used to record the remaining status of role allocation
    roles_pool: List[Role]
    players: Dict[str, User]  # Players in the room
    round: int  # round
    stage: Optional[GameStage]  # Game stage
    waiting: bool  # Waiting for player action
    # broadcast message source, (target, content)
    log: List[Tuple[Union[str, None], Union[str, LogCtrl]]]

    # Internal
    logic_thread: Optional[TaskHandle]

    async def night_logic(self):
        """Single Night Logic"""
        # start
        self.round += 1
        self.broadcast_msg("Please close your eyes when it's dark", tts=True)
        await asyncio.sleep(3)

        # werewolf
        self.stage = GameStage.WOLF
        self.broadcast_msg('Werewolf please appear', tts=True)
        await self.wait_for_player()
        self.broadcast_msg('Wolfman please close your eyes', tts=True)
        await asyncio.sleep(3)

        # Prophet
        if Role.DETECTIVE in self.roles:
            self.stage = GameStage.DETECTIVE
            self.broadcast_msg('The prophet please appear', tts=True)
            await self.wait_for_player()
            self.broadcast_msg('The prophet, please close your eyes', tts=True)
            await asyncio.sleep(3)

        # witch
        if Role.WITCH in self.roles:
            self.stage = GameStage.WITCH
            self.broadcast_msg('Witch please appear', tts=True)
            await self.wait_for_player()
            self.broadcast_msg('Witch please close your eyes', tts=True)
            await asyncio.sleep(3)

        # guard
        if Role.GUARD in self.roles:
            self.stage = GameStage.GUARD
            self.broadcast_msg('Guards please appear', tts=True)
            await self.wait_for_player()
            self.broadcast_msg('Guard, please close your eyes', tts=True)
            await asyncio.sleep(3)

        # hunter
        if Role.HUNTER in self.roles:
            self.stage = GameStage.HUNTER
            self.broadcast_msg('Hunter please appear', tts=True)
            await self.wait_for_player()
            self.broadcast_msg('Hunter please close your eyes', tts=True)
            await asyncio.sleep(3)

        # test result
        self.check_result()

    def check_result(self, is_vote_check=False):
        """Check results, called after voting and at the end of the night"""
        out_result = []  # This game is out
        # Survival list
        wolf_team = []
        citizen_team = []
        god_team = []
        for nick, user in self.players.items():
            if user.status in [
                PlayerStatus.ALIVE,
                PlayerStatus.PENDING_HEAL,
                PlayerStatus.PENDING_GUARD
            ]:
                if user.role in [Role.WOLF, Role.WOLF_KING]:
                    wolf_team.append(1)
                elif user.role in [Role.CITIZEN]:
                    citizen_team.append(1)
                else:
                    god_team.append(1)
                # set to ALIVE
                self.players[nick].status = PlayerStatus.ALIVE

            # set to DEAD
            if user.status in [PlayerStatus.PENDING_DEAD, PlayerStatus.PENDING_POISON]:
                self.players[nick].status = PlayerStatus.DEAD
                out_result.append(nick)

        if not citizen_team or (not self.is_no_god() and not god_team):
            self.stop_game('Wolfman wins')
            return

        if not wolf_team:
            self.stop_game('good guys win')
            return

        if not is_vote_check:
            self.stage = GameStage.Day
            self.broadcast_msg(
                f'it was dawn, last night {"no one" if not out_result else ",".join(out_result)} out', tts=True)
            self.broadcast_msg('waiting to vote')
            return

    async def vote_kill(self, nick):
        self.players[nick].status = PlayerStatus.DEAD
        self.check_result(is_vote_check=True)
        if self.started:
            self.enter_null_stage()
            await self.start_game()  # next night

    async def wait_for_player(self):
        """Player operation waiting for lock"""
        self.waiting = True
        while True:
            await asyncio.sleep(0.1)
            if self.waiting is False:
                self.broadcast_log_ctrl(LogCtrl.RemoveInput)
                break

    def enter_null_stage(self):
        """
        Set the current game stage to None

        Make sure to call this function "at the end of each phase logic" to keep the client UI state correct
        """
        self.stage = None

    async def start_game(self):
        """Start game/next night"""
        if not self.started:
            if self.logic_thread is not None and not self.logic_thread.closed():
                logger.error('The last game was not closed properly')
                return

            if len(self.players) != len(self.roles):
                self.broadcast_msg('Not enough people to start the game')
                return

            # game state
            self.started = True

            # assign identity
            self.broadcast_msg(
                'The game starts, please check your identity', tts=True)
            random.shuffle(self.roles_pool)
            for nick in self.players:
                self.players[nick].role = self.roles_pool.pop()
                self.players[nick].status = PlayerStatus.ALIVE
                # witch props
                if self.players[nick].role == Role.WITCH:
                    self.players[nick].skill['poison'] = True
                    self.players[nick].skill['heal'] = True
                # Guard guard record
                if self.players[nick].role == Role.GUARD:
                    self.players[nick].skill['last_protect'] = None
                self.players[nick].send_msg(
                    f'Your identity is "{self.players[nick].role}"')

            await asyncio.sleep(5)

        self.logic_thread = run_async(self.night_logic())

    def stop_game(self, reason=''):
        """End Game"""
        self.started = False
        self.roles_pool = copy(self.roles)
        self.round = 0
        self.enter_null_stage()
        self.waiting = False

        self.broadcast_msg(f'game over, {reason}.', tts=True)
        for nick, user in self.players.items():
            self.broadcast_msg(f'{nick}:{user.role}({user.status})')
            self.players[nick].role = None
            self.players[nick].status = None

    def list_alive_players(self) -> list:
        """Return surviving users, including players in PENDING_DEAD state"""
        return [user for user in self.players.values() if user.status != PlayerStatus.DEAD]

    def list_pending_kill_players(self) -> list:
        return [user for user in self.players.values() if user.status == PlayerStatus.PENDING_DEAD]

    def is_full(self) -> bool:
        return len(self.players) >= len(self.roles)

    def is_no_god(self):
        """The room is not equipped with a god"""
        god_roles = [Role.DETECTIVE, Role.WITCH, Role.HUNTER, Role.GUARD]
        for god in god_roles:
            if god in self.roles:
                return False
        return True

    def add_player(self, user: 'User'):
        """Add a user to the room"""
        if user.room or user.nick in self.players:
            raise AssertionError
        self.players[user.nick] = user
        user.room = self
        user.start_syncer()  # will run later

        players_status = f'Number of people {len(self.players)}/{len(self.roles)}, the host is {self.get_host()}'
        user.game_msg.append(players_status)
        self.broadcast_msg(players_status)
        logger.info(f'User "{user.nick}" joins room "{self.id}"')

    def remove_player(self, user: 'User'):
        """Remove user from room"""
        if user.nick not in self.players:
            raise AssertionError
        self.players.pop(user.nick)
        user.stop_syncer()
        user.room = None

        if not self.players:
            Global.remove_room(self.id)
            return

        self.broadcast_msg(
            f'Number of people {len(self.players)}/{len(self.roles)}, the host is {self.get_host()}')
        logger.info(f'User "{user.nick}" left room "{self.id}"')

    def get_host(self):
        if not self.players:
            return None
        return next(iter(self.players.values()))

    def send_msg(self, text: str, nick: str):
        """Send a message to the specified player, visible only to the specified player"""
        self.log.append((nick, text))

    def broadcast_msg(self, text: str, tts=False):
        """Broadcast a message to all players in the room"""
        if tts:
            say(text)

        self.log.append((Config.SYS_NICK, text))

    def broadcast_log_ctrl(self, ctrl_type: LogCtrl):
        """Broadcast special client control messages"""
        self.log.append((None, ctrl_type))

    def desc(self):
        return f'room number {self.id},' \
               f' requires players {len(self.roles)} people,' \
               f'staffing: {dict(Counter(self.roles))}'

    @classmethod
    def alloc(cls, room_setting) -> 'Room':
        """Create room by setting and register it to global storage"""
        # build full role list
        roles = []
        roles.extend([Role.WOLF] * room_setting['wolf_num'])
        roles.extend([Role.CITIZEN] * room_setting['citizen_num'])
        roles.extend(Role.from_option(room_setting['god_wolf']))
        roles.extend(Role.from_option(room_setting['god_citizen']))

        # Go
        return Global.reg_room(
            cls(
                id=None,
                # Static settings
                roles=copy(roles),
                witch_rule=WitchRule.from_option(room_setting['witch_rule']),
                guard_rule=GuardRule.from_option(room_setting['guard_rule']),
                # Dynamic
                started=False,
                roles_pool=copy(roles),
                players=dict(),
                round=0,
                stage=None,
                waiting=False,
                log=list(),
                # Internal
                logic_thread=None,
            )
        )

    @classmethod
    def get(cls, room_id) -> Optional['Room']:
        """Get an existing room"""
        return Global.get_room(room_id)

    @classmethod
    def validate_room_join(cls, room_id):
        room = cls.get(room_id)
        if not room:
            return 'The room does not exist'
        if room.is_full():
            return 'room is full'
