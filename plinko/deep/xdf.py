from collections import UserDict

class BetterDict(UserDict):
    def __add__(self, indict):
        if isinstance(indict, dict):
            copydict = self.data.copy()
            return copydict.update(indict)

    def __iadd__(self, indict):
        if isinstance(indict, dict):
            self.data.update(indict)
        return self
