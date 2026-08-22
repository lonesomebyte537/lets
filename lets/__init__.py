from lets.api import Lets, args, verb, DevContainer
from lets.core import LetsExcept, Password
import sys

def main():
    lets_instance = Lets()
    sys.exit(lets_instance._process_arguments(sys.argv[1:]))
