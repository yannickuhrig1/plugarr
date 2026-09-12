"""Keep local/CI test executables from being replaced by a public release."""
import os

os.environ['PLUGARR_NO_SELF_UPDATE'] = '1'
