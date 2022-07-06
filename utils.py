import random
import socket
import subprocess
import threading
import traceback
from logging import getLogger
from sys import platform

import pyttsx3

logger = getLogger('Utils')
logger.setLevel('DEBUG')


def rand_int(min_value=0, max_value=100):
    return random.randint(min_value, max_value)


def say(text):
    if platform == "darwin":
        subprocess.Popen(['say', '-r', '10000', text])
    elif platform == "win32":
        def wrapper():
            tts = pyttsx3.init()
            tts.say(text)
            tts.runAndWait()

        threading.Thread(target=wrapper).start()

    else:
        logger.warning(f'{platform} does not support TTS voice broadcast')


def get_interface_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0] or 'Get failed'
    except Exception:
        traceback.print_exc()
        return 'Get failed'


def add_cancel_button(buttons: list):
    return buttons + [{'label': 'cancel', 'type': 'cancel'}]
