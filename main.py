import asyncio
import sys
from logging import getLogger, basicConfig

from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.session import defer_call, get_current_task_id

from enums import WitchRule, GuardRule, Role, GameStage
from models.room import Room
from models.user import User
from utils import add_cancel_button, get_interface_ip

basicConfig(stream=sys.stdout,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = getLogger('Wolf')
logger.setLevel('DEBUG')


async def main():
    """Werewolf kill"""
    put_markdown("## werewolf kill judge")

    current_user = User.alloc(
        await input('Please enter your nickname',
                    required=True,
                    validate=User.validate_nick,
                    help_text='Please use a distinguished name'),
        get_current_task_id()
    )

    @defer_call
    def on_close():
        User.free(current_user)

    put_text(f'Hello, {current_user.nick}')
    data = await input_group(
        'Lobby', inputs=[actions(name='cmd', buttons=['Create room', 'Join room'])]
    )

    if data['cmd'] == 'Create room':
        room_config = await input_group('Room settings', inputs=[
            input(name='wolf_num', label='Number of ordinary wolves',
                  type=NUMBER, value='3'),
            checkbox(name='god_wolf', label='Special wolf',
                     inline=True, options=Role.as_god_wolf_options()),
            input(name='citizen_num', label='Number of ordinary villagers',
                  type=NUMBER, value='4'),
            checkbox(name='god_citizen', label='Special villager',
                     inline=True, options=Role.as_god_citizen_options()),
            select(name='witch_rule', label='Witch Antidote Rule',
                   options=WitchRule.as_options()),
            select(name='guard_rule', label='Guard Rule',
                   options=GuardRule.as_options()),
        ])
        room = Room.alloc(room_config)
    elif data['cmd'] == 'Join room':
        room = Room.get(await input('room number', type=TEXT, validate=Room.validate_room_join))
    else:
        raise NotImplementedError

    put_scrollable(current_user.game_msg, height=200, keep_bottom=True)
    current_user.game_msg.append(put_text(room.desc()))

    room.add_player(current_user)

    while True:
        await asyncio.sleep(0.2)
        # Non-night homeowner operation
        host_ops = []
        if current_user is room.get_host():
            if not room.started:
                host_ops = [
                    actions(name='host_op', buttons=[
                            'Start game'], help_text='You are the host')
                ]
            elif room.stage == GameStage.Day and room.round > 0:
                host_ops = [
                    actions(
                        name='host_vote_op',
                        buttons=[
                            user.nick for user in room.list_alive_players()],
                        help_text='You are the homeowner, you need to choose a player to be eliminated in this round'
                    )
                ]

        # player action
        user_ops = []
        if room.started:
            if room.stage == GameStage.WOLF and current_user.should_act():
                user_ops = [
                    actions(
                        name='wolf_team_op',
                        buttons=add_cancel_button(
                            [user.nick for user in room.list_alive_players()]),
                        help_text='Werewolf camp, please select the target to kill. '
                    )
                ]
            if room.stage == GameStage.DETECTIVE and current_user.should_act():
                user_ops = [
                    actions(
                        name='detective_team_op',
                        buttons=[
                            user.nick for user in room.list_alive_players()],
                        help_text='Prophet, please select the object to check. '
                    )
                ]
            if room.stage == GameStage.WITCH and current_user.should_act():
                if current_user.witch_has_heal():
                    current_user.send_msg(
                        f' was killed last night is {room.list_pending_kill_players()}')
                else:
                    current_user.send_msg('You have no antidote')

                user_ops = [
                    radio(name='witch_mode', options=[
                          'antidote', 'poison'], required=True, inline=True),
                    actions(
                        name='witch_team_op',
                        buttons=add_cancel_button(
                            [user.nick for user in room.list_alive_players()]),
                        help_text='Witch, please choose your action. '
                    )
                ]
            if room.stage == GameStage.GUARD and current_user.should_act():
                user_ops = [
                    actions(
                        name='guard_team_op',
                        buttons=add_cancel_button(
                            [user.nick for user in room.list_alive_players()]),
                        help_text='Guard, please choose your action. '
                    )
                ]
            if room.stage == GameStage.HUNTER and current_user.should_act():
                current_user.hunter_gun_status()

        ops = host_ops + user_ops
        if not ops:
            continue

        # UI
        if host_ops + user_ops:
            current_user.input_blocking = True
        data = await input_group('Operation', inputs=host_ops + user_ops, cancelable=True)
        current_user.input_blocking = False

        # Canceled
        if data is None:
            current_user.skip()
            continue

        # Host logic
        if data.get('host_op') == 'Start game':
            await room.start_game()
        if data.get('host_vote_op'):
            await room.vote_kill(data.get('host_vote_op'))
        # Wolf logic
        if data.get('wolf_team_op'):
            current_user.wolf_kill_player(nick=data.get('wolf_team_op'))
        # Detective logic
        if data.get('detective_team_op'):
            current_user.detective_identify_player(
                nick=data.get('detective_team_op'))
        # Witch logic
        if data.get('witch_team_op'):
            if data.get('witch_mode') == 'antidote':
                current_user.witch_heal_player(nick=data.get('witch_team_op'))
            elif data.get('witch_mode') == 'Poison':
                current_user.witch_kill_player(nick=data.get('witch_team_op'))
        # Guard logic
        if data.get('guard_team_op'):
            current_user.guard_protect_player(nick=data.get('guard_team_op'))


if __name__ == '__main__':
    logger.info(
        f"The Werewolf Killing Server was started successfully! You can join the game by entering http://{get_interface_ip()} in the browser")
    start_server(main, debug=False, cdn=False)
