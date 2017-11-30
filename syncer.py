import subprocess
import argparse
import textwrap
import re
import json
from pprint import pprint as pp
from collections import OrderedDict


class AssertionErrorWithInfo(AssertionError):
    def __init__(self, message, more_info=None):
        self.more_info = more_info
        super(AssertionErrorWithInfo, self).__init__(message)


def post_send_command_actions(cmd, exp_rc, out, err, rc):
    if exp_rc is not None and not isinstance(exp_rc, list):
        exp_rc = [int(exp_rc)]
    elif exp_rc is not None:
        exp_rc = [int(item) for item in exp_rc]

    if exp_rc is not None:
        if rc not in exp_rc:
            raise AssertionErrorWithInfo(
                "Error occurred  during '%s' execution: "
                "got rc='%s' but expected %s. \nError: %s" % (
                    cmd, rc, exp_rc, err))
    return out, err


def subprocess_send_command(cmd, exp_rc=0):
    sub_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    out, err = sub_process.communicate()
    rc = sub_process.returncode
    out1, err1 = post_send_command_actions(cmd, exp_rc, out, err, rc)
    return out1, err1, rc


class RsyncCommandBuilder(object):
    def __init__(self, path_to_files, remote_host):
        self.command = ['rsync']
        self.remote_host = remote_host
        self.path_to_files = path_to_files
        self.port = None
        self.password = None
        self.summary = None
        self.partial_progress = None
        self.progress = None
        self.remote_shell = None

    def set_password(self, value):
        self.password = value
        return self

    def set_summary(self, value):
        self.summary = value
        return self

    def set_partial_progress(self, value):
        self.partial_progress = value
        return self

    def set_progress(self, value):
        self.progress = value
        return self

    def set_remote_shell(self, value):
        self.remote_shell = value
        return self

    def _verify_non_standard_port(self):
        pattern = r'\w+[\,,\.,\:](?P<name>\d+)@'
        found_data = re.findall(pattern, self.remote_host)
        if found_data:
            self.port = found_data[0]
            self.remote_host = re.sub(r'.{0}'.format(self.port), '',
                                      self.remote_host)
            self.remote_shell = True
        return self

    def build_command(self):
        if self.password:
            self.command.append("-pass='{0}'".format(self.password))
        if self.summary:
            self.command.append("-i")
        if self.partial_progress:
            self.command.append("-P")
        if self.progress:
            self.command.append("--progress")
        self._verify_non_standard_port()
        if self.remote_shell:
            if self.port:
                self.command.append('-e ssh -p {0}'.format(self.port))
            else:
                self.command.append("-e ssh")
        self.command.extend(self.path_to_files)
        self.command.append(self.remote_host)
        return self.command


class Parser(object):
    def __init__(self, string):
        self.string = string
        self.output_dict = OrderedDict()
        self.column_names = ['Size', 'Percentage', 'Speed', 'Time left']
        self.template = (r'(?P<first>\d+)\s+'
                         r'(?P<second>\d+\%)\s+'
                         r'(?P<third>\d+.\d+\w+\/s)\s+'
                         r'(?P<fourth>\d+\:\d+\:\d+)')

    def to_parse(self):
        data = re.compile(self.template)
        matched_data = re.findall(data, self.string)
        for single_match in matched_data:
            i = 0
            dict_to_insert = dict()
            for name in self.column_names:
                if i == 1:
                    pass
                else:
                    dict_to_insert[name] = single_match[i]
                i += 1
            if single_match[1] == '100%':
                interval_key = "Synchronization finished {}"\
                    .format(single_match[1])
            else:
                interval_key = "Percentage: {}"\
                    .format(single_match[1])
            self.output_dict[interval_key] = dict_to_insert
        return self.output_dict


class ResultBuilder(object):
    def __init__(self, output, error, exit_code):
        self.output = output
        self.error = error
        self.exit_code = exit_code

    def build_json(self):
        data_as_dict = {
            'error': str(self.error),
            'result': self.output,
            'status': self.exit_code
        }
        json_data = json.dumps(data_as_dict, sort_keys=True,
                               indent=4, separators=(',', ': '))
        return json_data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='My Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent('''\
                    Wrapper for Linux native 'rsync' utility
                    --------------------------------
                    Provides an easy way to replicate 
                    files from local to remote host!'''))
    parser.add_argument('-progress', action='store_true',
                        help='show progress during transfer')
    parser.add_argument('-e', '--rsh', help='specify the remote shell to use')
    parser.add_argument('-P', action='store_true',
                        help='same as --partial --progress')
    parser.add_argument('-i', action='store_true',
                        help='output a change-summary for all updates')
    parser.add_argument('-pass', '--password',
                        help='read daemon-access password from FILE')
    parser.add_argument('path_to_folder', nargs='*', help='path to folder')
    parser.add_argument('name_and_host',
                        help='username and hostname of remote host')
    args = parser.parse_args()
    command = RsyncCommandBuilder(args.path_to_folder, args.name_and_host)\
        .set_partial_progress(args.P).set_password(args.password)\
        .set_progress(args.progress)\
        .set_remote_shell(args.rsh)\
        .set_summary(args.i)\
        .build_command()
    try:
        output, error, exit_code = subprocess_send_command(command)
        parsed_output = Parser(output).to_parse()
        # pp(ResultBuilder(parsed_output, error, exit_code).build_json())
        with open("output.txt", 'w') as file:
            file.write(ResultBuilder(parsed_output, error, exit_code)
                       .build_json())
    except Exception as e:
        print e

