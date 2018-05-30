import json
import os

# processes compile_commands.json to remove duplicate entries and add extra entries

def process_compile_commands(cc_filename, extra_cc_filename):
    print('Processing compile_commands')
    cc_file = open(cc_filename, 'r')
    extra_cc_file = None
    if os.path.isfile(extra_cc_filename):
        extra_cc_file = open(extra_cc_filename, 'r')
    compile_commands = json.load(cc_file)
    file_set = set()
    new_compile_commands = []
    for f in compile_commands:
        if f['file'] not in file_set:
            file_set.add(f['file'])
            new_compile_commands.append(f)
    if extra_cc_file:
        extra_compile_commands = json.load(extra_cc_file)
        for f in extra_compile_commands:
            new_compile_commands.append(f)
        extra_cc_file.close()
    cc_file.close()
    cc_file = open(cc_filename, 'w')
    json.dump(new_compile_commands, cc_file)
    cc_file.close()

