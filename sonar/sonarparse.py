#!/usr/bin/env python3
''' Ping Sonar Ping Viewer binary log (.bin) file parser.
    Operates as a generator.
'''

from decode_sensor_binary_log import PingViewerLogReader, Ping1DSettings
from datetime import time, timedelta, datetime
from pathlib import Path
from csv import writer
import pandas as pd

class Ping1DDistances(PingViewerLogReader):
    distance_messages = {
        1211, # distance_simple
        1212, # distance
        1300, # profile
    }

    def __init__(self, filename: str, timezone: str):
        ''' Create a Ping1D Log reader with timezone localisation.

        'timezone' should be one of pytz.all_timezones.
          Most common formats are Region/City
            (e.g. Australia/Melbourne, US/Eastern, Pacific/Tahiti),
          and Etc/GMT+offset (e.g. Etc/GMT+11, Etc/GMT-6).

        '''
        super().__init__(filename)
        self.timezone = timezone
        self.start_time = (pd.to_datetime(Path(filename).stem,
                                          format='%Y%m%d-%H%M%S%f')
                           .tz_localize(timezone))
        self.tzinfo = self.start_time.tzinfo

    def distance_estimates(self):
        ''' yields triplets of (timestamp, distance, confidence). '''
        for timestamp, message in self.parser(self.distance_messages):
            # localize timezone and remove Windows extra null bytes
            timestamp = self.start_time \
                + self.timedelta(timestamp.replace('\x00',''))
            yield timestamp, *self.get_distance(timestamp, message)

    def get_distance(self, timestamp, message):
        ''' Return the distance estimate and confidence from a message.

        Intentionally abstracted out to simplify using alternative distance
          estimation metrics from, profile post-processing or more exact
          sound speed from consideration of water properties and telemetry.

        '''
        return message.distance, message.confidence

    def to_csv(self, output: str):
        if output is None:
            output = Path(self.filename).with_suffix('.csv')
        
        adding = Path(output).is_file()
        with open(output, 'a') as out:
            csv = writer(out)
            if not adding:
                csv.writerow(('timestamp','distance [mm]', 'confidence'))
            for data in self.distance_estimates():
                csv.writerow(data)

    @classmethod
    def logs_to_csv(cls, output, logs, timezone):
        for log in logs:
            cls(log, timezone).to_csv(output)

    @staticmethod
    def timedelta(time_str: str) -> timedelta:
        ''' Return a timedelta from an iso-format time string. '''
        delta = time.fromisoformat(time_str)
        return timedelta(hours=delta.hour, minutes=delta.minute,
                         seconds=delta.second, microseconds=delta.microsecond)

if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+',
                        help='log file(s)/path(s) to parse.')
    parser.add_argument('-s', '--sort', action='store_true',
                        help='flag to sort file names')
    parser.add_argument('-tz', '--timezone', required=True, type=str,
                        help='local timezone (e.g. US/Eastern, Etc/GMT+11)')
    parser.add_argument('-o', '--output', default=None, type=str,
                        help=('output filename '
                              '(defaults to existing log name(s) for csv). '
                              'If specified, combines all logs into one csv.'))

    args = parser.parse_args()

    files = args.files
    if args.sort:
        # sort lexicographically by file name
        #  -> for standard log files means earliest file comes first
        files = sorted(files, key=lambda path: Path(path).stem)

    Ping1DDistances.logs_to_csv(args.output, args.files, args.timezone)
