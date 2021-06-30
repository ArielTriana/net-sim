from pathlib import Path
from exception import MissConfigFileException, UnknowKeyOfConfigException
from shutil import rmtree
from os import mkdir, chdir
import json

BUNDLE_CONFIG = "__exec__"
BUNDLE_OUTPUT = "output"

class Initializer:
    def __init__(self, config_name = "config.txt"):

        self._CONFIG_FILE_NAME = config_name
        self.config = {}

        Initializer.clean_output_file()

    def load_config(self):
        path_config = Path(f"{BUNDLE_CONFIG}/{self._CONFIG_FILE_NAME}")

        if path_config.exists():
            with open(path_config) as f:
                self.config = json.load(f)
        else:
            raise MissConfigFileException()

    def get(self, key):
        if key in self.config:
            return self.config[key]
        raise UnknowKeyOfConfigException(key)

    @staticmethod
    def clean_output_file():
        output_path = Path(BUNDLE_OUTPUT)
        if output_path.exists():
            rmtree(str(output_path))
        mkdir(str(output_path))

