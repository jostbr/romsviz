
# ============================================================================================
# TODO (enhance): Consider implementing a namelist approach for info such as dim names, titles/labels and colormaps
# TODO (enhance): Add support for creating subplots in existing figure passed to the various plotting methods
# TODO (enhance): Consider supporting dpeth-horizontal slices not parallell to coordinate axes
# TODO (enhance): Support user inputting **plot_kwargs and pass onto the plot/contourf/... functions
# TODO (enhance): Better error handling ensuring correct dimension limits from user before calling get_var()
# TODO (enhance): Support animation of vertical crossections too
# TODO (issue): Specifying range for both x and y is currently "allowed" in depth_csection()
# ============================================================================================

# general modules
import json
import datetime as dt
import numpy as np
import matplotlib.pyplot as plt
import mpl_toolkits.axes_grid1
import cartopy

# other ROMS specific modules
import roppy    # needed to convert from sigma- to z-coordinates
import cmocean  # for colormaps

# module(s) part of this package
from . import ncout

class RomsViz(ncout.NetcdfOut):
    def __init__(self, filename, varinfo_file="romsviz/varinfo.json"):
        super(RomsViz, self).__init__(filename)
        self.varinfo_file = varinfo_file
        self.default_title_fs = 20
        self.default_label_fs = 15
        plt.style.use("seaborn-deep")
        plt.rc("font", family="serif")
        self.var_info = self.load_varinfo(varinfo_file)

    def set_gridfile(self, filename):
        """Method docstring..."""
        self.gridfile = ncout.NetcdfOut(filename)

    def load_varinfo(self, infofile):
        """Method docstring..."""
        with open(infofile, "r") as nl:
            return json.load(nl)

    def time_series(self, var_name, figax=None, **limits):
        """Method docstring..."""
        var = self.get_var(var_name, **limits)
        ranged_coors = ["t"]
        self.check_range_dims(var, ranged_coors)

        # plot time series with dates on the x-axis
        fig, ax = self._get_figax(figsize=(12,5), figax=figax)
        ax.plot(var.time, var.data, linewidth=1)
        ax.grid(True)

        name = var.attr_to_string(var.meta, ["long_name", "standard_name"])
        ylabel = var.attr_to_string(var.meta, "units")
        limits_str = var.lims_to_str(exclude=[var.time_name])
        ax.set_title("{} {}".format(name, limits_str))
        ax.set_ylabel("{}".format(ylabel))
        ax = self._set_default_txtprop(ax)

        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        fig.tight_layout()

        return fig, ax

    def depth_time_contour(self, var_name, figax=None, **limits):
        """Method docstring..."""
        var = self.get_var(var_name, **limits)
        ranged_coors = ["z", "t"]
        self.check_range_dims(var, ranged_coors)

        z = self.get_sdepths(var)

        # plot depth time contour with dates on the x-axis
        fig, ax = self._get_figax(figsize=(12,5), figax=figax)

        try:
            cs = ax.contourf(var.time, z, var.data.transpose(), cmap=self.cmaps[var.name])
        except KeyError:
            cs = ax.contourf(var.time, z, var.data.transpose(), cmap=self.cmaps["default"])

        # colorbar stuff
        divider = mpl_toolkits.axes_grid1.make_axes_locatable(ax)
        cax = divider.append_axes("right", size="2.5%", pad=0.15)
        cbar_label = var.attr_to_string(var.meta, "units")
        cb = plt.colorbar(cs, cax=cax, label=cbar_label, orientation="vertical")

        # title and labels
        name = var.attr_to_string(var.meta, ["long_name", "standard_name"])
        limits_str = var.lims_to_str(exclude=[var.time_name, "s_rho"])
        ax.set_title("{} {}".format(name, limits_str))
        ax.set_ylabel("Depth [m]")
        ax = self._set_default_txtprop(ax)

        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")  # rotate xlabel
        fig.tight_layout()

        return fig, ax

    def csection(self, var_name, figax=None, lonlat=False, **limits):
        """Method docstring..."""
        var = self.get_var(var_name, **limits)
        range_dims = var.get_range_dims(enforce=2)
        xaxis_name = self.vardim_to_axisdim(var.name, "xaxis", range_dims)
        yaxis_name = self.vardim_to_axisdim(var.name, "yaxis", range_dims)
        x_axis = self.get_var(xaxis_name, **self._var2var_limits(xaxis_name, **limits))
        y_axis = self.get_var(yaxis_name, **self._var2var_limits(yaxis_name, **limits))

        print(var.data.mask)

        # plot time series with dates on the x-axis
        fig, ax = self._get_figax(figsize=(12,5), figax=figax)
        cs = ax.contourf(x_axis.data, y_axis.data, np.ma.masked_where(var.data==var.data.max(), var.data), 50, cmap=cmocean.cm.thermal)

        # colorbar stuff
        divider = mpl_toolkits.axes_grid1.make_axes_locatable(ax)
        cax = divider.append_axes("right", size="2.5%", pad=0.15)
        #cbar_label = var.attr_to_string(var.meta, "units")
        cbar_label = "hax"
        cb = plt.colorbar(cs, cax=cax, label=cbar_label, orientation="vertical")

        # title and labels
        #name = var.attr_to_string(var.meta, ["long_name", "standard_name"])
        limits_str = var.lims_to_str(exclude=[var.time_name, "s_rho"])
        ax.set_title("{} {}".format("hax", limits_str))
        ax.set_ylabel("Depth [m]")
        ax = self._set_default_txtprop(ax)

        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")  # rotate xlabel
        fig.tight_layout()

        return fig, ax

    def horizontal_csection(self, var_name, figax=None, **limits):
        """Method docstring..."""
        limits["s_rho"] = 41  # default to surface
        raise NotImplementedError

    def vardim_to_axisdim(self, var_name, axis_name, range_dims):
        """Method docstring..."""
        for rd in range_dims:
            if self.var_info["dimensions"][rd] in self.var_info[var_name]["csection"][axis_name]:
                return self.var_info["dimensions"][rd]

        raise ValueError("No dim in {} found in {}".format(range_dims, self.var_info[var_name]["csection"][axis_name]))

    def lonlat_from_lims(self, x_lim, y_lim):
        """Method docstring..."""
        raise NotImplementedError
        lon_var = self.get_var("lon_rho", xi_rho=x_lim, eta_rho=y_lim)
        lat_var = self.get_var("lat_rho", xi_rho=x_lim, eta_rho=y_lim)
        return lon_var, lat_var

    def get_map(self, **map_kwargs):
        """Method docstring..."""
        raise NotImplementedError
        if len(map_kwargs) == 0:
            map_kwargs = self.map_kwargs_from_netcdf()

        return Basemap(**map_kwargs)

    def map_kwargs_from_netcdf(self):
        raise NotImplementedError

    def get_sdepths(self, var):
        """Method docstring..."""
        # get necessary variables for the vertical grid
        h = self.get_var("h").data
        H_c = float(self.get_var("hc").data)
        vtrans = float(self.get_var("Vtransform").data)

        # prepare indices for what slice to extract
        x_name = var.identify_dim(self.coors["x"])
        y_name = var.identify_dim(self.coors["y"])
        z_name = var.identify_dim(self.coors["z"])
        xlim = var.get_lim(x_name)
        ylim = var.get_lim(y_name)
        zlim = var.get_lim(z_name)
        slices = self._lims_to_slices([zlim, ylim, xlim])

        # variable defined at rho s-levels
        if z_name == "s_rho":
            C = self.get_var("Cs_r").data
            z = roppy.sdepth(h, H_c, C, Vtransform=vtrans, stagger="rho")[slices]

        # variable defined at w s-levels
        elif z_name == "s_w":
            C_w = self.get_var("Cs_w").data
            z = roppy.sdepth(h, H_c, C_w, Vtransform=vtrans, stagger="w")[slices]

        return z.squeeze()

    def images_to_mp4(self, method="convert"):
        """Method docstring..."""
        raise NotImplementedError
        if method == "convert":
            subprocess.call("convert -loop 0 -delay 10 -hax 1 {} {}".format(wildcard, output_fn))

        elif method == "builtin":
            anim = animation.FuncAnimation()
            anim.save(output_fn)

    def _get_figax(self, figsize=(12,7), figax=None):
        if figax is None:
            return plt.subplots(figsize=figsize, facecolor="white")

        else:
            return figax[0], figax[1]

    def _set_default_txtprop(self, ax):
        #ax.title.set_fontname(self.default_title_fn)
        #ax.xaxis.get_label().set_fontname(self.default_label_fn)
        #ax.yaxis.get_label().set_fontname(self.default_label_fn)
        ax.title.set_fontsize(self.default_title_fs)
        ax.xaxis.get_label().set_fontsize(self.default_label_fs)
        ax.yaxis.get_label().set_fontsize(self.default_label_fs)
        return ax

    def __str__(self):
        raise NotImplementedError("Hax!")
