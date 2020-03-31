import argparse
import struct
import os
from dataclasses import dataclass
from typing import List

__author__ = "Brian Schlining"
__copyright__ = "Copyright 2020, Monterey Bay Aquarium Research Institute"


@dataclass
class log_record:
    """ This class contains a single field defined in the header of the binary file and the data
    associated with that field.

        data_type: integer, timeTag, angle, double, etc
        short_name: time, hours, latitide, etc
        long_name: Vehicle latityte, Geoidal separation, etc.
        units: For what they're worth in the log files
        instrument_name: parser just uses the name of the soruce file, e.g. `gps.log`
        data: A list of the data from the file. 
    """
    data_type: str
    short_name: str
    long_name: str
    units: str
    instrument_name: str
    data: List

    def length(self):
        n = 8
        if self.data_type == 'float':
            n = 4
        elif self.data_type == 'integer':
            n = 4
        elif self.data_type == 'short':
            n = 2
        return n


def read(file: str) -> List[log_record]:
    """Reads and parses an AUV log and returns a list of `log_records`
    """
    byte_offset = 0
    records = []
    (byte_offset, records) = _read_header(file)
    _read_data(file, records, byte_offset)
    return records


def _read_header(file: str):
    """Parses the ASCII header of the log file
    """
    with open(file, 'r', encoding="ISO-8859-15") as f:
        byte_offset = 0
        records = []
        instrument_name = os.path.basename(f.name)

        # Yes, read 2 lines here.
        line = f.readline()
        line = f.readline()
        while line:
            if "begin" in line:
                break
            else:
                # parse line
                ssv = line.split(" ")
                data_type = ssv[1]
                short_name = ssv[2]

                csv = line.split(",")
                long_name = csv[1]
                units = csv[2]
                if short_name == 'time':
                    units = 'seconds since 1970-01-01 00:00:00Z'
                r = log_record(data_type, short_name, long_name,
                               units, instrument_name, [])
                records.append(r)

            line = f.readline()
            byte_offset = f.tell()
        return (byte_offset, records)


def _read_data(file: str, records: List[log_record], byte_offset: int):
    """Parse the binary section of the log file
    """
    ok = True
    with open(file, 'rb') as f:
        f.seek(byte_offset)
        while ok:
            for r in records:
                b = f.read(r.length())
                if not b:
                    ok = False
                    break
                s = "<d"
                if r.data_type == "float":
                    s = "<f"
                elif r.data_type == "integer":
                    s = "<i"
                elif r.data_type == "short":
                    s = "<h"
                v = struct.unpack(s, b)[0]
                r.data.append(v)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Read an AUV binary log')
    parser.add_argument("logfile", type=str,
                        help="The name of the log to read")
    args = parser.parse_args()
    records = read(args.logfile)
    print(records)
