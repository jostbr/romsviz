
class OutVar(object):
    """Class representing a output variable generated in the NetcdfOut.get_var() method.
    When extracting a variable from a netcdf file, an instance of this class will be
    created and all relevant info on the extracted variable is stored as attributes
    to that instance. Although, the class is meant as support to the NetcdfOut class,
    one might find uses outside of that too. Various methods working on the attributes
    are defined below as well.
    """
    def __init__(self):
        """Constructor setting all attributes to None. They are expected
        to be modified externally (e.g. by the NetcdfOut class)."""
        self.name = None
        self.meta = None
        self.lims = None
        self.time_dist = None
        self.use_files = None
        self.dim_names = None
        self.data = None
        self.time_name = None
        self.time = None

    def extract_lim(self, dim_name):
        """
        Function that extracts the index limits for a dimension.

        Args:
            dim_name (str) : Name of dimesnion tog et index limtis for
        Returns:
            lims (tuple) : (start, end) index of requested dim
        """
        for i in range(len(self.dim_names)):
            if self.dim_names[i] == dim_name:
                return self.lims[i]

        raise ValueError("{} is not a dimension of {}!".format(
                         dim_name, self.var_name))

    def identify_dim(self, suggestions):
        """
        Function that checks if variable has one of the suggested dimensions.

        Args:
            suggestions (list) : List of name sggestions for dimensions
        Returns:
            dim_name (str) : Name of dim first matching with a suggestion
        """
        for dim_name in self.dim_names:
            for d in suggestions:
                if dim_name == d:
                    return dim_name

        raise ValueError("No dimension of {} are in <suggestions>".format(self.name))

    def attr_to_string(self, obj, attr):
        """
        Function that gives the string value of the requested attribute.

        Args:
            obj (type(obj))  : Some object whos string attribute to get
            attr (str, list) : Attribute(s) names to get string value for
        Returns:
            attr_string (str) : String value of requested attribute
        """
        if type(attr) is str:
            attr = [attr]  # need to be list below

        for a in attr:
            val = getattr(obj, a, None)

            if val:
                return val.encode("utf8").capitalize()

        return "N/A"

    def lims_to_str(self, exclude=list()):
        """
        Function that converts self's lims to a string

        Args:
            exclude (list) : List of dim names to exclude in teh string
        Returns:
            lims_str (str) : String representation of self's lims
        """
        lims_str = "("

        for d_name, lim in zip(self.dim_names, self.lims):
            if d_name not in exclude:
                if lim[0] == lim[1]:
                    lims_str += "{}: {}".format(d_name, lim[0])

                else:
                    lims_str += "{}: {}".format(d_name, lim)

                if d_name != self.dim_names[-1]:
                    lims_str += ", "

        return lims_str + ")"

    def __str__(self):
        """Print representation of ocject as of now...""""
        if self.var_meta is None:
            return self.name

        else:
            return self.meta
