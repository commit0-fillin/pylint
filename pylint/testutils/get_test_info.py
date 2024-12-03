from __future__ import annotations
from glob import glob
from os.path import basename, join, splitext
from pylint.testutils.constants import SYS_VERS_STR

def _get_tests_info(input_dir: str, msg_dir: str, prefix: str, suffix: str) -> list[tuple[str, str]]:
    """Get python input examples and output messages.

    We use following conventions for input files and messages:
    for different inputs:
        test for python  >= x.y    ->  input   =  <name>_pyxy.py
        test for python  <  x.y    ->  input   =  <name>_py_xy.py
    for one input and different messages:
        message for python >=  x.y ->  message =  <name>_pyxy.txt
        lower versions             ->  message with highest num
    """
    result = []
    for fname in glob(join(input_dir, prefix + "*" + suffix)):
        infile = basename(fname)
        fbase = splitext(infile)[0]
        # Handle the case for python version specific test files
        if fbase.endswith(SYS_VERS_STR):
            message_file = join(msg_dir, fbase + '.txt')
        else:
            # Find the highest version message file
            message_files = glob(join(msg_dir, fbase + '_py*.txt'))
            message_file = max(message_files, default='')
        
        if message_file:
            result.append((infile, basename(message_file)))
    
    return result
