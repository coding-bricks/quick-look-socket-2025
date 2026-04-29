import sys
from ichnos.app import main

if __name__ == "__main__":
    # passa argomenti CLI al tuo sistema
    sys.argv = ["ichnos"] + sys.argv[1:]
    main()
