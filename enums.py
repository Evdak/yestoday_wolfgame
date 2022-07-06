from enum import Enum
from typing import Union


class LogCtrl(Enum):
    """Broadcast target is None, special control message type enumeration"""
    RemoveInput = 'Remove the current input box'


class PlainEnum(Enum):

    def __repr__(self):
        return self.value

    __str__ = __repr__


class PlayerStatus(PlainEnum):
    ALIVE = 'Alive'
    DEAD = 'Out'
    PENDING_DEAD = 'Killed by Werewolf/Witch/rescue conflict'
    PENDING_HEAL = 'Freed by a Witch'
    PENDING_POISON = 'Poisoned by a Witch'
    PENDING_GUARD = 'Guarded by guards'


class GameStage(Enum):
    Day = 'Day'
    WOLF = 'Wolfman'
    DETECTIVE = 'Prophet'
    WITCH = 'Witch'
    GUARD = 'Guard'
    HUNTER = 'Hunter'


class Role(PlainEnum):
    WOLF = 'Werewolf'  # Werewolf
    WOLF_KING = 'Wolf King'  # Wolf King
    DETECTIVE = 'The Prophet'  # the seer
    WITCH = 'Witch'  # Witch
    GUARD = 'Guard'  # guard
    HUNTER = 'Hunter'  # hunter
    CITIZEN = 'Civilian'  # Civilian

    @classmethod
    def as_god_citizen_options(cls) -> list:
        return list(cls.god_citizen_mapping().keys())

    @classmethod
    def as_god_wolf_options(cls) -> list:
        return list(cls.god_wolf_mapping().keys())

    @classmethod
    def from_option(cls, option: Union[str, list]):
        if isinstance(option, list):
            return [cls.mapping()[item] for item in option]
        elif isinstance(option, str):
            return cls.mapping()[option]
        else:
            raise NotImplementedError

    @classmethod
    def normal_mapping(cls) -> dict:
        return {
            'Wolfman': cls.WOLF,
            'Civilian': cls.CITIZEN,
        }

    @classmethod
    def god_wolf_mapping(cls) -> dict:
        return {
            'Wolf King': cls.WOLF_KING
        }

    @classmethod
    def god_citizen_mapping(cls) -> dict:
        return {
            'Prophet': cls.DETECTIVE,
            'Witch': cls.WITCH,
            'Guard': cls.GUARD,
            'Hunter': cls.HUNTER,
        }

    @classmethod
    def mapping(cls) -> dict:
        return dict(**cls.normal_mapping(), **cls.god_wolf_mapping(), **cls.god_citizen_mapping())


class WitchRule(Enum):
    SELF_RESCUE_FIRST_NIGHT_ONLY = 'Only the first night can save yourself'
    NO_SELF_RESCUE = 'No self-rescue'
    ALWAYS_SELF_RESCUE = 'Always save yourself'

    @classmethod
    def as_options(cls) -> list:
        return list(cls.mapping().keys())

    @classmethod
    def from_option(cls, option: Union[str, list]):
        if isinstance(option, list):
            return [cls.mapping()[item] for item in option]
        elif isinstance(option, str):
            return cls.mapping()[option]
        else:
            raise NotImplementedError

    @classmethod
    def mapping(cls) -> dict:
        return {
            'Only the first night can save yourself': cls.SELF_RESCUE_FIRST_NIGHT_ONLY,
            'Always save yourself': cls.ALWAYS_SELF_RESCUE,
            'No self-rescue': cls.NO_SELF_RESCUE,
        }


class GuardRule(Enum):
    MED_CONFLICT = 'The subject dies when being rescued at the same time'
    NO_MED_CONFLICT = 'The object survives when being defended and rescued at the same time'

    @classmethod
    def as_options(cls) -> list:
        return list(cls.mapping().keys())

    @classmethod
    def from_option(cls, option: Union[str, list]):
        if isinstance(option, list):
            return [cls.mapping()[item] for item in option]
        elif isinstance(option, str):
            return cls.mapping()[option]
        else:
            raise NotImplementedError

    @classmethod
    def mapping(cls) -> dict:
        return {
            'The object dies when guarded and rescued at the same time': cls.MED_CONFLICT,
            'The object survives when being guarded and rescued at the same time': cls.NO_MED_CONFLICT,
        }
