VERSION = '2.6.5'
DEBUG = True
CREATE_DEBUG_UNITS = True  # Only creates them if `DEBUG` is True

# Shell script `zip_project.sh` relies on these print statements
print("lambdanaut-v{}".format(VERSION))
print("DEBUG MODE: {}".format(DEBUG))
