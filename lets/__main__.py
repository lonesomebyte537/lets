import sys
from . import Lets

def main():
    lets_instance = Lets()
    sys.exit(lets_instance._process_arguments(sys.argv[1:]))

if __name__ == "__main__":
    main()
