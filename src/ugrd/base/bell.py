__author__ = "desultory"
__version__ = "0.1.0"


def startup_bell(self) -> str:
    """ Prints the bell symbol if the bell var is set """
    return """
    if check_var bell; then
        printf '\a'
    fi
    """

def end_bell(self) -> str:
    """ Prints the bell symbol twice if the bell var is set """
    return """
    if check_var bell; then
        printf '\a\a'
    fi
    """

def export_bell(self) -> None:
    """ Adds the bell variable to the exports dict """
    self["exports"]["bell"] = 1 if self["bell"] else 0
