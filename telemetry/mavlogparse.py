#!/usr/bin/env python3
''' Mavlink telemetry (.tlog) file parser.
    Operates as a generator. Allows csv output or listing useful types/fields.
'''

import json
import pandas as pd
from pathlib import Path
from fnmatch import fnmatch
from pymavlink import mavutil
from inspect import getfullargspec


class Telemetry:
    DEFAULT_FIELDS = {
        'VFR_HUD'          : ['heading', 'alt', 'climb'],
        'VIBRATION'        : [f'vibration_{axis}' for axis in 'xyz'],
        'SCALED_IMU2'      : [s for axis in 'xyz'
                              for s in (axis+'acc', axis+'gyro')],
        'ATTITUDE'         : [s for rot in ('roll', 'pitch', 'yaw')
                              for s in (rot, rot+'speed')],
        'SCALED_PRESSURE2' : ['temperature'],
    }
    def __init__(self, log_file, fields=DEFAULT_FIELDS,
                 dialect='ardupilotmega'):
        ''' Creates a tlog parser on 'log_file', extracting 'fields'.
        'log_file' can be a string filename/path, or pathlib.Path instance.
        'fields' is either a dictionary in the form {'TYPE': ['attr']/None},
            or a string filename/path to a json/text file with the same
            structure. Specifying None (null if in a file) instead of an
            attribute list gets all the attributes for that type.
            Defaults to Telemetry.DEFAULT_FIELDS.
        'dialect' is a string specifying the mavlink parsing dialect to use.
            Default 'ardupilotmega'.
        '''
        self.log_file = str(log_file) # mavutil doesn't use Path 
        self.mlog = mavutil.mavlink_connection(self.log_file, dialect=dialect)

        self._init_fields(fields)

    def _init_fields(self, fields):
        ''' Determine CSV fields and populate None attribute lists. '''
        if isinstance(fields, (str, Path)):
            with open(fields) as field_file:
                fields = json.load(field_file)

        self.csv_fields = ['timestamp']
        nan = float('nan') # start with non-number data values
        self.data = [nan]
        self.offsets = {}
        for type_, field in fields.items():
            if field is None:
                type_class = f'MAVLink_{type_.lower()}_message'
                fields[type_] = \
                    getfullargspec(getattr(mavutil.mavlink,
                                           type_class).__init__).args[1:]
            self.offsets[type_] = offset = len(self.csv_fields)
            self.csv_fields.extend(f'{type_}.{attr}' for attr in fields[type_])
            self.data.extend(nan for _ in range(len(self.csv_fields) - offset))

        self.fields = fields
        self.type_set = set(fields) # put major fields in a set

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.mlog.close()

    def __iter__(self):
        ''' Iterate through available messages. '''
        while msg := self.mlog.recv_match(type=self.type_set):
            m_type = msg.get_type()

            if m_type == 'BAD_DATA':
                print('bad data recorded')
                continue
            elif not self.match_types(m_type, self.type_set):
                # keep going if the message is the wrong type
                # NOTE: specifically relevant because recv_match internal
                #       'skip_to_type' function auto-includes HEARTBEAT and
                #       PARAM_VALUE messages
                continue

            yield msg

    @staticmethod
    def match_types(m_type, patterns):
        ''' Return True if m_type matches one of patterns.
        'patterns' are types but case-insensitive on Windows, and with support
            for unix-style wildcards:
                *      -> match everything
                ?      -> match a single character
                [seq]  -> match any character in seq
                [!seq] -> match any character not in seq
        '''
        return any(fnmatch(m_type, p) for p in patterns)

    def to_csv(self, output=None, csv_sep=',', verbose=True):
        '''
        NOTE: opens output in append mode
               -> can create files, but WILL NOT overwrite existing files
                  (adds to the end instead).
        '''
        if output is None:
            output = Path(self.log_file).with_suffix('.csv')
        if verbose:
            print(f'Processing {self.log_file}\n  -> Saving to {output}')

        last_timestamp = None
        adding = Path(output).is_file()
        # TODO enable stdout output for printing to terminal?
        with self as mavlink, open(output, 'a') as out_file:
            def write_line(data):
                print(csv_sep.join(data), file=out_file)
            # convert to suitable for csv output
            self.data = [str(val) for val in self.data]

            if not adding:
                write_line(self.csv_fields) # field headings

            for msg in mavlink:
                wrote_last = False
                timestamp = getattr(msg, '_timestamp', 0.0)
                data = msg.to_dict()
                if last_timestamp is not None and timestamp != last_timestamp:
                    # new timestamp, so write latest data and timestamp
                    self.data[0] = f'{last_timestamp:.8f}'
                    write_line(self.data)
                    wrote_last = True

                self._update(msg.get_type(), data, convert=str)
                last_timestamp = timestamp

            try:
                if not wrote_last: # handle last message
                    self.data[0] = f'{last_timestamp:.8f}'
                    write_line(self.data)
            except UnboundLocalError:
                print('No desired messages found in file')

    def data_parser(self):
        last_timestamp = None
        with self as mavlink:
            for msg in mavlink:
                yielded_last = False
                timestamp = getattr(msg, '_timestamp', 0.0)
                data = msg.to_dict()
                if last_timestamp is not None and timestamp != last_timestamp:
                    # new timestamp, so yield latest data and timestamp
                    self.data[0] = last_timestamp
                    yield self.data
                    yielded_last = True

                self._update(msg.get_type(), data)
                last_timestamp = timestamp

            try:
                if not yielded_last: # handle last message
                    self.data[0] = last_timestamp
                    yield self.data
            except UnboundLocalError:
                print('No desired messages found in file')

    def _update(self, type_, data, convert=lambda d: d):
        ''' Update with the latest data for 'type_'. '''
        offset = self.offsets[type_]
        for index, desired_attr in enumerate(self.fields[type_]):
            self.data[offset+index] = convert(data[desired_attr])

    @classmethod
    def logs_to_csv(cls, output, logs, fields=DEFAULT_FIELDS, csv_sep=',',
                    dialect='ardupilotmega', verbose=True):
        for log in logs:
            cls(log, fields, dialect).to_csv(output, csv_sep, verbose)

    @staticmethod
    def csv_to_df(filename, timestamp='timestamp',
                  timezone='Australia/Melbourne', **kwargs):
        ''' Returns a pandas dataframe of a csv-log, indexed by timestamp.
        'filename' is the path to a csv-file, as output by Telemetry.to_csv
        'timestamp' is the name of the timestamp column. Defaults to
            "timestamp".
        'timezone' is the location where the data was collected. Data is
            assumed to be in UTC, and is converted to the specified timezone.
            Defaults to 'Australia/Melbourne'.
        'kwargs' are additional key-word arguments to pass to pandas read_csv.
            Mostly useful for 'usecols', if not all columns are required.
        '''
        def parser(utc_epoch_seconds):
            return (pd.to_datetime(utc_epoch_seconds, unit='s')
                    .tz_localize('utc').tz_convert(timezone))

        return pd.read_csv(filename, index_col=timestamp,
                           parse_dates=[timestamp], date_parser=parser,
                           **kwargs)

    @classmethod
    def get_useful_fields(cls, tlogs, out='useful.json', fields=None,
                          dialect='ardupilotmega', verbose=True):
        ''' Returns a {type: [fields]} dictionary of all non-constant fields.
        'tlogs' should be an iterable of one or more string/Path filepaths.
        'out' is the filename to save to. If set to None does not save.
        'fields' a json file for a subset of fields to parse with. If left as
            None checks all fields in the file.
        'dialect' is the mavlink dialect in use. Default 'ardupilotmega'.
        'verbose' a boolean determining if progress updates should be printed.
        '''
        mavutil.set_dialect(dialect) # set dialect so field tracker is accurate
        fields = cls.__create_field_tracker(fields)
        # determine fields dictionary to initialise with
        init_fields = {type_: list(fields_)
                       for type_, fields_ in fields.items()}

        useful_types = {}

        for tlog in tlogs:
            if verbose:
                print(f'Extracting useful fields from {tlog!r}')
            with cls(tlog, init_fields, dialect) as mavlink:
                for msg in mavlink:
                    cls.__process(msg, mavlink, fields, init_fields,
                                  useful_types)

        useful_types = {t: useful_types[t] for t in sorted(useful_types)}

        if out:
            with open(out, 'w') as output:
                json.dump(useful_types, output, indent=4)
            if verbose:
                print(f'  -> Saving to {output}')

        return useful_types

    @staticmethod
    def __create_field_tracker(fields):
        ''' Create a dictionary of {type: {field: None}} for specified fields.
        If 'fields' is None gets all the types and fields from mavutil.mavlink.
        If 'fields' is a string/Path json file, reads in and replaces any
            None fields with all the valid fields for that type.
        '''
        def get_fields(type_):
            ''' Return a dict of {field: None} for all fields of type_. '''
            return {field: None for field in
                    getfullargspec(getattr(mavutil.mavlink,
                                           type_).__init__).args[1:]}

        if fields is None:
            fields = {t[8:-8].upper(): get_fields(t)
                      for t in dir(mavutil.mavlink)
                      if t.startswith('MAVLink_') and t.endswith('_message')}
        elif isinstance(fields, (str, Path)):
            fmt = 'MAVLink_{}_message'
            with open(fields) as in_file:
                fields = {type_: ({field: None for field in fields_} if fields_
                                  else get_fields(fmt.format(type_.lower())))
                          for type_, fields_ in json.load(in_file).items()}

        return fields

    @staticmethod
    def __process(msg, mavlink, fields, init_fields, useful_types):
        msg_type = msg.get_type()

        to_remove = []
        for field, data in fields[msg_type].items():
            msg_data = getattr(msg, field)
            if data is None:
                fields[msg_type][field] = msg_data
            elif msg_data != data:
                # data changes -> useful field
                if msg_type not in useful_types:
                    useful_types[msg_type] = []
                useful_types[msg_type].append(field)
                to_remove.append(field)
                if not fields[msg_type]:
                    # all fields useful -> stop checking type
                    mavlink.type_set.pop(msg_type)
                    init_fields.pop(msg_type)

        for field in to_remove:
            fields[msg_type].pop(field)


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser(description=__doc__)
    parser.add_argument('-o', '--output', default=None, type=str,
                        help=('output filename '
                              '(defaults to existing tlog name(s) for csv,'
                              ' no default if using --list - specify json'
                              ' filename if desired)'))
    parser.add_argument('-f', '--fields', default=None, type=str,
                        help='fields subset to parse with (json file)')
    parser.add_argument('-d', '--dialect', default='ardupilotmega', type=str,
                        help='mavlink dialect to parse with')
    parser.add_argument('-t', '--tlogs', required=True, nargs='*',
                        help='tlog filename(s)/path(s) to parse')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list useful (non-constant) fields')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='turn off printed output')

    args = parser.parse_args()
    verbose = not args.quiet

    if args.list:
        fields = Telemetry.get_useful_fields(args.tlogs, args.output,
                                             args.fields, args.dialect,
                                             verbose)
        if verbose:
            print(json.dumps(fields, indent=4))
    else:
        fields = args.fields or Telemetry.DEFAULT_FIELDS
        Telemetry.logs_to_csv(args.output, args.tlogs, fields, verbose=verbose)
