#!/usr/bin/env python
"""
Align calibrated data producing a netCDF file with coordinates on each variable

Read calibrated data from netCDF files created by calibrate.py, use the
best available (e.g. filtered, nudged) coordinate variables to interpolate
onto each each measured (record) variable sampling interval. The original 
instrument sampling interval is preserved with the coordinate varaibles 
interpolated onto that original time axis.
"""

__author__ = "Mike McCann"
__copyright__ = "Copyright 2021, Monterey Bay Aquarium Research Institute"

import argparse
import logging
import os
import sys
import time
from argparse import RawTextHelpFormatter
from datetime import datetime
from socket import gethostname

import cf_xarray  # Needed for the .cf accessor
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from scipy.interpolate import interp1d

from logs2netcdfs import BASE_PATH, MISSIONNETCDFS


class Align_NetCDF:
    logger = logging.getLogger(__name__)
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        "%(levelname)s %(asctime)s %(filename)s "
        "%(funcName)s():%(lineno)d %(message)s"
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    _log_levels = (logging.WARN, logging.INFO, logging.DEBUG)

    def global_metadata(self):
        """Use instance variables to return a dictionary of
        metadata specific for the data that are written
        """
        iso_now = datetime.utcnow().isoformat() + "Z"

        metadata = {}
        metadata["netcdf_version"] = "4"
        metadata["Conventions"] = "CF-1.6"
        metadata["date_created"] = iso_now
        metadata["date_update"] = iso_now
        metadata["date_modified"] = iso_now
        metadata["featureType"] = "trajectory"

        ##metadata["time_coverage_start"] = str(
        ##    self.aligned_nc["depth_time"].to_pandas()[0].isoformat()
        ##)
        ##metadata["time_coverage_end"] = str(
        ##    self.aligned_nc["depth_time"].to_pandas()[-1].isoformat()
        ##)
        metadata[
            "distribution_statement"
        ] = "Any use requires prior approval from MBARI"
        metadata["license"] = metadata["distribution_statement"]
        metadata[
            "useconst"
        ] = "Not intended for legal use. Data may contain inaccuracies."
        metadata["history"] = f"Created by {self.commandline} on {iso_now}"

        metadata["title"] = (
            f"Calibrated and aligned AUV sensor data from"
            f" {self.args.auv_name} mission {self.args.mission}"
        )
        metadata["summary"] = (
            f"Observational oceanographic data obtained from an Autonomous"
            f" Underwater Vehicle mission with measurements at"
            f" original sampling intervals. The data have been calibrated"
            f" and the coordinate variables aligned using MBARI's auv-python"
            f" software."
        )
        metadata["comment"] = (
            f"MBARI Dorado-class AUV data produced from original data"
            f" with execution of '{self.commandline}'' at {iso_now} on"
            f" host {gethostname()}. Software available at"
            f" 'https://bitbucket.org/mbari/auv-python'"
        )

        return metadata

    def process_cal(self, vehicle: str = None, name: str = None) -> None:
        name = name or self.args.mission
        vehicle = vehicle or self.args.auv_name
        netcdfs_dir = os.path.join(self.args.base_path, vehicle, MISSIONNETCDFS, name)
        in_fn = f"{vehicle}_{name}_cal.nc"
        self.calibrated_nc = xr.open_dataset(os.path.join(netcdfs_dir, in_fn))
        logging.info(f"Processing {in_fn} from {netcdfs_dir}")
        self.aligned_nc = xr.Dataset()
        for variable in self.calibrated_nc.keys():
            instr, _ = variable.split("_")
            self.logger.debug(f"instr: {instr}")
            if instr in ("navigation", "gps", "depth", "nudged"):
                continue
            # Process variables from seabird25p, ctd1, ctd2, hs2, ...
            self.logger.info(f"Processing {variable}")
            self.aligned_nc[variable] = self.calibrated_nc[variable]
            # Interpolators for the non-time dimensions
            lat_interp = interp1d(
                self.calibrated_nc["nudged_latitude"]
                .get_index("time")
                .astype(np.int64)
                .tolist(),
                self.calibrated_nc["nudged_latitude"].values,
                fill_value="extrapolate",
            )
            lon_interp = interp1d(
                self.calibrated_nc["nudged_longitude"]
                .get_index("time")
                .astype(np.int64)
                .tolist(),
                self.calibrated_nc["nudged_longitude"].values,
                fill_value="extrapolate",
            )
            depth_interp = interp1d(
                self.calibrated_nc["depth_filtdepth"]
                .get_index("depth_time")
                .astype(np.int64)
                .tolist(),
                self.calibrated_nc["depth_filtdepth"].values,
                fill_value="extrapolate",
            )
            var_time = (
                self.aligned_nc[variable]
                .get_index(f"{instr}_time")
                .astype(np.int64)
                .tolist()
            )
            # Create new DataArrays of all the variables, including "aligned"
            # (interpolated) depth, latitude, and longitude coordinates.
            # Use attributes from the calibrated data.
            self.aligned_nc[variable] = xr.DataArray(
                self.calibrated_nc[variable].values,
                dims={f"{instr}_time"},
                coords=[self.calibrated_nc[variable].get_index(f"{instr}_time")],
                name=variable,
            )
            self.aligned_nc[variable].attrs = self.calibrated_nc[variable].attrs
            self.aligned_nc[variable].attrs[
                "coordinates"
            ] = f"{instr}_time {instr}_depth {instr}_latitude {instr}_longitude"
            self.aligned_nc[variable].attrs["instrument_sample_rate_hz"] = np.round(
                1.0
                / (
                    np.mean(np.diff(self.calibrated_nc[f"{instr}_time"]))
                    / np.timedelta64(1, "s")
                ),
                decimals=2,
            )

            self.aligned_nc[f"{instr}_depth"] = xr.DataArray(
                depth_interp(var_time).astype(np.int64).tolist(),
                dims={f"{instr}_time"},
                coords=[self.calibrated_nc[variable].get_index(f"{instr}_time")],
                name=f"{instr}_depth",
            )
            self.aligned_nc[f"{instr}_depth"].attrs = self.calibrated_nc[
                "depth_filtdepth"
            ].attrs
            self.aligned_nc[f"{instr}_depth"].attrs["comment"] += (
                f". Variable depth_filtdepth from {in_fn} file interpolated"
                f" onto {variable} time values."
            )

            self.aligned_nc[f"{instr}_latitude"] = xr.DataArray(
                lat_interp(var_time).astype(np.int64).tolist(),
                dims={f"{instr}_time"},
                coords=[self.calibrated_nc[variable].get_index(f"{instr}_time")],
                name=f"{instr}_latitude",
            )
            self.aligned_nc[f"{instr}_latitude"].attrs = self.calibrated_nc[
                "depth_filtdepth"
            ].attrs
            self.aligned_nc[f"{instr}_latitude"].attrs["comment"] += (
                f". Variable nudged_latitude from {in_fn} file interpolated"
                f" onto {variable} time values."
            )

            self.aligned_nc[f"{instr}_longitude"] = xr.DataArray(
                lon_interp(var_time).astype(np.int64).tolist(),
                dims={f"{instr}_time"},
                coords=[self.calibrated_nc[variable].get_index(f"{instr}_time")],
                name=f"{instr}_longitude",
            )
            self.aligned_nc[f"{instr}_longitude"].attrs = self.calibrated_nc[
                "depth_filtdepth"
            ].attrs
            self.aligned_nc[f"{instr}_longitude"].attrs["comment"] += (
                f". Variable nudged_longitude from {in_fn} file interpolated"
                f" onto {variable} time values."
            )

        return netcdfs_dir

    def write_netcdf(self, netcdfs_dir, vehicle: str = None, name: str = None) -> None:
        name = name or self.args.mission
        vehicle = vehicle or self.args.auv_name
        self.aligned_nc.attrs = self.global_metadata()
        out_fn = os.path.join(netcdfs_dir, f"{vehicle}_{name}_align.nc")
        self.logger.info(f"Writing aligned data to {out_fn}")
        if os.path.exists(out_fn):
            self.logger.debug(f"Removinf file {out_fn}")
            os.remove(out_fn)
        self.aligned_nc.to_netcdf(out_fn)
        self.logger.info(
            "Data variables written: %s", ", ".join(sorted(self.aligned_nc.variables))
        )

    def process_command_line(self):

        examples = "Examples:" + "\n\n"
        examples += "  Align calibrated data for some missions:\n"
        examples += "    " + sys.argv[0] + " --mission 2020.064.10\n"
        examples += "    " + sys.argv[0] + " --auv_name i2map --mission 2020.055.01\n"

        parser = argparse.ArgumentParser(
            formatter_class=RawTextHelpFormatter,
            description=__doc__,
            epilog=examples,
        )

        parser.add_argument(
            "--base_path",
            action="store",
            default=BASE_PATH,
            help=f"Base directory for missionlogs and missionnetcdfs, default: {BASE_PATH}",
        )
        parser.add_argument(
            "--auv_name",
            action="store",
            default="Dorado389",
            help="Dorado389 (default), i2MAP, or Multibeam",
        )
        parser.add_argument(
            "--mission",
            action="store",
            help="Mission directory, e.g.: 2020.064.10",
        )
        parser.add_argument(
            "--plot",
            action="store_true",
            help="Create intermediate plots to validate data operations.",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            type=int,
            choices=range(3),
            action="store",
            default=0,
            const=1,
            nargs="?",
            help="verbosity level: "
            + ", ".join(
                [f"{i}: {v}" for i, v, in enumerate(("WARN", "INFO", "DEBUG"))]
            ),
        )
        self.args = parser.parse_args()
        self.logger.setLevel(self._log_levels[self.args.verbose])
        self.commandline = " ".join(sys.argv)


if __name__ == "__main__":

    align_netcdf = Align_NetCDF()
    align_netcdf.process_command_line()
    p_start = time.time()
    netcdf_dir = align_netcdf.process_cal()
    align_netcdf.write_netcdf(netcdf_dir)
    align_netcdf.logger.info(f"Time to process: {(time.time() - p_start):.2f} seconds")
