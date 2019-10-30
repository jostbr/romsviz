
# ============================================================================================
# TODO: (issue) Some more docstrings
# TODO: (enhance) Consider storing full time array (across files) in __init__ (if exists) and use it for dim lims later
# TODO: (enhance) Possibly move datatype checking in _get_dim_lims() to _verify_kwargs()
# TODO: (issue) Using netCDF4.num2date() with var.units is risky
# TODO: (enhance) Add support for opening each of the nc-files when they are read and not in __ini__()
# ============================================================================================

import os
import sys
import glob
import logging
import collections
import datetime as dt
import numpy as np
import netCDF4
from . import outvar

class NetcdfOut(object):
    """Class docstring...

    Important Assumptions:
        * If called with wildcard or list of multiple filenames, all data in the different
          files are assumed to be of the same structure (all variables are present with same
          shape in all files), only difference being the elements in the time array. Also,
          automatic expansion of the wildcard is assumed to list the files in the correct order.
        * There are only one unlimited dimension and that is time.
    """
    def __init__(self, filename, debug=False):
        """
        Constructor function that sets attributes and opens all input files.
        Also extracts the dimensions of the dataset for later use. Also
        enables/disables logging for debugging purposes.

        Args:
            filename (str/list) : Path/wildcard/list to netcdf data file(s)
            debug (bool)        : True/False to turn on/off debug mode
        """
        if debug:
            logging.basicConfig(level=logging.NOTSET)
            logging.info("debug mode enabled!")
        else:
            logging.basicConfig(level=logging.CRITICAL)

        self.filename = filename
        self.filepaths = self.generate_filepaths()
        self.time_name = self._get_unlimited_dim()
        self.default_lim = (None, None)

    def generate_filepaths(self):
        """
        Method that parses instance attribute self.filename and interpretates it
        as either a string (can be wildcard) or list and gives back list of filenames.

        Returns:
            filepaths (list(str)) : List of all filenames matching self.filename
        """
        if type(self.filename) is str:
            filepaths = sorted(glob.glob(self.filename))  # expand potential wildcard and sort
        elif type(self.filename) is list:
            filepaths = self.filename             # keep user inputed list
        else:
            raise TypeError("{} must be str or list".format(self.filename))

        if not filepaths:
            raise IOError("Invalid path(s) {}!".format(self.filename))

        # quick check to see that all files exists
        for fn in filepaths:
            if not os.path.exists(fn):
                raise IOError("File does not exist: {}!".format(fn))

        return filepaths

    def _get_unlimited_dim(self):
        """Method that finds the unlimited dimension in the dataset. Returns
        (None, None) if no nunlimited dimension is found in the dataset).

        Returns:
            dim_name (str)          : Name of unlimited dimension
            dim (netCDF4.Dimension) : Dimension object for unlimtied dim
        """
        with netCDF4.Dataset(self.filepaths[0], mode="r") as ds:
            for dim_name, dim in ds.dimensions.items():
                if dim.isunlimited():
                    return str(dim_name)

        return None

    def get_var(self, var_name, **limits):
        """
        Method that supervises the fetching of data from a certain netcdf output
        variable. User may define index limits for all dimensions (or only some of
        them) of the variable if e.g. only parts of the simulation time or domain is
        of interest.

        Args:
            var_name (str)      : Name of variable to be extracted
            limits (str: tuple) : Lower- and upper index limits for a dimension to
                                  the variable. Min index is 0 and max index is the
                                  size of the particular dimension. Limits for a
                                  dimension defaults to (0, dim.size).
        Returns:
            var (OutVar) : Custom variable object containing info about the
                           extracted variable including a data array within
                           the index limits specified. If the variable has a
                           time dimension, the object contains a datetime array
                           for the relevant time range of the extracted variable.
        """
        logging.debug("extracting variable {}".format(var_name))
        logging.debug("user supplied dimension limits: {}".format(limits))

        # store info in OutVar object and verify user inputed dimension limits
        var = outvar.OutVar()
        var.name = var_name
        var.dim_names = self._get_var_attr(self.filepaths[0], var_name, "dimensions")
        self._verify_kwargs(var.name, var.dim_names, **limits)
        var.lims = self._get_dim_lims(var.dim_names, **limits)
        var.bounds = list(self._get_var_attr(self.filepaths[0], var_name, "shape"))

        # the time dimension may span over multiple files
        if self.time_name in var.dim_names:
            self.set_time_array()
            t_idx = var.dim_names.index(self.time_name)
            var.bounds[t_idx] = self._get_num_time_entries()
            var.lims[t_idx] = self._get_time_lims(var.lims[t_idx], var.bounds[t_idx])
            self._verify_lims(var.lims, var.bounds, var.dim_names)
            var.use_files, var.t_dist = self._compute_time_dist(*var.lims[t_idx])

            data_list = list()
            lims = var.lims[:]

            # loop through the all data sets and extract data if inside time limits
            for i, fn in enumerate(self.filepaths):
                if var.use_files[i]:
                    lims[t_idx] = var.t_dist[i]
                    slices = self._lims_to_slices(lims)
                    logging.debug("getting data from file {} with slices {}".format(fn, slices))

                    with netCDF4.Dataset(fn, mode="r") as ds:
                        data_list.append(self._get_var_nd(var.name, slices, ds))

            # concatenate data from (possibly) multiple files along time axis
            data = np.concatenate(data_list, axis=t_idx)
            var.time = self.time[self._lims_to_slices([var.lims[t_idx]])]  # include time slice

        # very simple if there's no time dimension
        else:
            self._verify_lims(var.lims, var.bounds, var.dim_names)
            slices = self._lims_to_slices(var.lims)

            with netCDF4.Dataset(self.filepaths[0], mode="r") as ds:
                data = self._get_var_nd(var.name, slices, ds)  # use e.g. zeroth dataset

        var.data = data.squeeze()  # finally store the main array in var object
        return var

    def _get_var_attr(self, filename, var_name, attr):
        """
        Method that gives an attribute for a variable in a netcdf file.

        Args:
            filename (str)    : Name of file with variable
            var_name (string) : Name of variable
            attr (str)        : Name of attribute to get
        Returns:
            attr (some type) : The requested attribute if it exists
        """
        with netCDF4.Dataset(filename, mode="r") as ds:
            if var_name not in ds.variables.keys():
                raise ValueError("Invalid variable {}!".format(var_name))

            return getattr(ds.variables[var_name], attr)

    def _get_dim_lims(self, vd_names, **limits):
        """
        Method that extracts user provided keyword arguments for
        dimension index limits and constructs a list of with the limits
        being in the exact same order as the actual dimensions variable.

        Args:
            vd_names (list) : List of actual variable dimension names
            limits (dict)   : See limits in self.get_var()
        """
        idx_lims = list()

        # loop over all actual dimensions of the variable
        for vd_name in vd_names:

            # fill limits if missing kwarg for any dimension
            if vd_name not in limits.keys():
                lim = self.default_lim  # default to entire range

            # if user gives e.g. int, float, dt.datetime
            elif type(limits[vd_name]) not in [tuple, list]:
                lim = (limits[vd_name], limits[vd_name])

            # if user has given tuple or list of limits
            else:
                lim = limits[vd_name]

            idx_lims.append(lim)  # store user inputed limits

        return idx_lims

    def _get_range_dims(self, dim_names, lims):
        """
        Method that finds out what dimensions have limits are over a
        range, i.e. not a single index, but spanning several.

        Args:
            dim_names (list) : List of dimension names
            lims (list)      : List of tuples with index limits for each dimension
        """
        range_dims = list()

        for d_name, lim in zip(dim_names, lims):
            if lim[1] != lim[0] or None in lim:
                range_dims.append(d_name)

        return range_dims

    def _verify_kwargs(self, var_name, vd_names, **limits):
        """
        Method that raises error if not all dimension names
        specified in limits are in valid dimensions for the variable.

        Args:
            limits (dict) : See limits in self.get_var()
        """
        for key in limits.keys():
            if key not in vd_names:
                raise ValueError("Variable {} has no dimension {}!".format(var_name, key))

    def _verify_lims(self, lims, bounds, vd_names):
        """
        Method that verifies if the user provided index limits on
        the requested variable are within bounds, raises error if not.

        Args:
            lims (list)     : List of tuples with index limits
            bounds (list)   : List of upper index bounds
            vd_names (list) : List of actual variable dimension names
        """
        # check that specified dimension limits are valid
        for (l_1, l_2), length, vd_name in zip(lims, bounds, vd_names):
            if (l_1, l_2) == self.default_lim:
                continue  # nothing to check if default limits

            valid_lims = l_1 >= 0 and l_1 <= length and l_2 >= 0 and l_2 <= length

            if not valid_lims:
                raise ValueError("Index limits {} are outside (0, {}) for {}!".format(
                                 (l_1, l_2), length, vd_name))

            if l_2 < l_1:
                raise ValueError("Lower index {} larger than upper {} for {}!".format(
                                 l_1, l_2, vd_name))

    def _get_num_time_entries(self):
        """
        Method that counts number of total time entries (across files).

        Returns:
            num_time_entries (int) : Number of time elements across all input files
        """
        time_length = 0

        for fn in self.filepaths:
            with netCDF4.Dataset(fn, mode="r") as ds:
                time_length += ds.variables[self.time_name].shape[0]

        return time_length

    def set_time_array(self):
        """
        Method that stitches together the time array over all files.

        Returns:
            t_dates (np.ndarray (1D)) : Full time array across all files
        """
        t_dates = list()

        for fn in self.filepaths:
            with netCDF4.Dataset(fn, mode="r") as ds:
                t_raw = ds.variables[self.time_name]
                t_dates.append(netCDF4.num2date(t_raw[:], t_raw.units))

        self.time = np.concatenate(t_dates, axis=0)

    def _get_time_lims(self, t_lim, total_length):
        """
        Method that handles user provided time limits and returns
        index limits spanning (possibly) over several files.

        Args:
            lims (list) : Start- and end limits for time (can
                          be both datetime or indices (int))
        """
        int_types = [int, np.int8, np.int16, np.int32, np.int64]

        if t_lim == self.default_lim:
            return (0, total_length - 1)

        elif type(t_lim[0]) in int_types or type(t_lim[1]) in int_types:
            return t_lim

        elif type(t_lim[0]) is dt.datetime:
            idx_start = self._idx_from_date(t_lim[0])
            idx_stop = self._idx_from_date(t_lim[1])
            return (idx_start, idx_stop)

        else:
            raise TypeError("Invalid limits {} for {} (use int/datetime/None)".format(
                t_lim, self.time_name))

    def _idx_from_date(self, date):
        """
        Method that finds the index of a given date.

        Args:
            date (datetime) : Date to find index for
        Returns:
            idx (int) : Index of the specified date
        """
        idx = np.where(self.time == date)  # assume only 1 occurrence of date

        if len(idx[0]) == 0:
            raise ValueError("Date {} not in {}!".format(date, self.time_name))

        return idx[0][0]

    def _compute_time_dist(self, idx_start, idx_stop):
        """
        Method that computes the time indices to extract across files, thus
        tells what indices to extract from what files.

        Args:
            idx_start (int) : Starting index of total time slice
            idx_stop (int)  : Stop index of total time slice
        """
        t_per_file = list()

        for fn in self.filepaths:
            with netCDF4.Dataset(fn, mode="r") as ds:
                t_per_file.append(ds.variables[self.time_name].shape[0])

        use_files = [False for _ in t_per_file]  # bool values for relevant files
        idx_total = 0       # to count total indices over all files

        # compute in what file contains idx_start and idx_stop
        for i in range(len(t_per_file)):
            for j in range(t_per_file[i]):
                if idx_start == idx_total:
                    file_start = i          # file index for time start
                    i_start = j             # start index within that file

                if idx_stop == idx_total:
                    file_stop = i           # file index for time stop
                    i_stop = j              # stop index within that file

                idx_total += 1

        use_files[file_start] = True
        use_files[file_stop] = True

        # structure to tell, in what file and what index, the specified time starts and stops
        t_dist = [[None, None] for _ in range(len(self.filepaths))]  # default (None, None)
        t_dist[file_start][0] = i_start  # file and idx for start time
        t_dist[file_stop][1] = i_stop    # file and idx for stop time

        t_dist = tuple(tuple(d) for d in t_dist)  # convert to tuples for safety

        # fill use_files with True between "start" and "end" files
        trues = [i for i, el in enumerate(use_files) if el is True]

        if len(trues) == 2 and trues[1] - trues[0] != 1:  # done already if not this
            use_files[trues[0]+1:trues[1]] = [True for _ in range(trues[1]-trues[0]-1)]

        return use_files, t_dist

    def _lims_to_slices(self, lims):
        """
        Method that converts a list of index limits to a list of index slices,
        i.e. each tuple of index limits in the list is expanded to a slice covering
        all covering the indexes between the end points.

        Args:
            lims (list) : List of tuples with index limits for each dimension
        """
        slices = list()

        for l in lims:
            if l[1] is not None:
                slices.append(slice(l[0], l[1] + 1))  # include end point too

            else:
                slices.append(slice(l[0], l[1]))

        return tuple(slices)

    def _get_var_nd(self, var_name, slices, dataset):
        """
        Method that reads an n-dimensional variable from a dataset.

        Args:
            var_name (str)    : Name of variable to read
            slices (tuple)    : Tuple of slice objects (one for each dimension)
                                for indexing the variable
            dataset (Dataset) : The dataset to read from
        """
        return dataset.variables[var_name][slices]

    def _var2var_limits(self, var_name, **limits):
        """
        Method that takes in a set of dimension limits and keeps only the ones
        that apply with the specified variable.

        Args:
            var_name (str) : Name of variable to extract limits for
            limits (dict)  : Dict of limits from e.g. some other variable
                             to extract a subset of for <var_name>
        """
        with netCDF4.Dataset(self.filepaths[0], mode="r") as ds:
            return {k: v for k, v in limits.items() if k in ds.variables[var_name].dimensions}
