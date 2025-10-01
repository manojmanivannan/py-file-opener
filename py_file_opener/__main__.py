import sys, os
from time import sleep
from subprocess import call, check_call

try:
    __import__("inquirer")
except ImportError:
    if str(
        input('Functionality requires package "Inquirer", proceed to install ? (y/n) ')
    ).lower() in [
        "yes",
        "y",
    ]:
        check_call([sys.executable, "-m", "pip", "install", "inquirer==2.9.2"])
    else:
        print("Exiting..")
        sys.exit(1)

import inquirer
from inquirer.themes import GreenPassion
import re
from difflib import SequenceMatcher

OKGREEN = "\033[32m"
WARNING = "\033[33m"
FAIL = "\033[31m"
ENDC = "\033[0m"


def get_matching_word(string1, string2):
    match = SequenceMatcher(None, string1, string2).find_longest_match(
        0, len(string1), 0, len(string2)
    )
    return string1[match.a : match.a + match.size]


def separate_path_and_file(path_list, match_word):
    common_dir = os.path.dirname(match_word)
    print(
        OKGREEN + "Common Path:" + ENDC + " " + WARNING + common_dir + ENDC,
        file=sys.stdout,
    )
    files = [x.replace(common_dir, "") for x in path_list]
    return common_dir, files


def get_root_file_list(path_list):
    new_matched_word = os.path.commonprefix(path_list)
    return separate_path_and_file(path_list, new_matched_word)


def main():
    os.chdir(sys.argv[1])
    cwd = os.getcwd()
    path_list = sys.argv[2:]
    if len(path_list) == 1:
        print("Opening:", sys.argv[2])
        sleep(0.5)
        call(["vim", sys.argv[2]])
        sys.exit(0)

    root_dir, file_list = get_root_file_list(path_list)
    questions = [
        inquirer.List(
            "size",
            message="which file? ",
            choices=file_list,
        )
    ]
    answers_ = inquirer.prompt(questions, theme=GreenPassion())
    try:
        chosen = answers_["size"]
    except:
        sys.exit(1)

    full_file_path = root_dir + chosen
    print("Opening:", full_file_path)
    sleep(0.5)
    call(["vim", full_file_path])


if __name__ == "__main__":
    main()
