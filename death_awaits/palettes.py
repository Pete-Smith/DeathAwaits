import sys
import copy
import random

import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widgets


class BasePalette:
    """
    Client code uses a palette object by passing in a name
    and getting back a color hex code.
    Use the get_application_palette function in this module to grab the current
    palette.
    Palette objects are persisted for a whole session and remember which colors
    are assigned for which names.
    The palette tries to give repeat names colors that they've been assigned
    before.
    """

    def __init__(self):
        self._past_assignments = dict()
        self.refresh()

    def __len__(self):
        return len(self.colors)

    def refresh(self):
        """ Refresh the pool of available colors for a new chart/graph. """
        self.available_colors = copy.copy(self.colors)
        self.available_colors.reverse()

    def colors(self):
        """
        The sub-class' colors attribute should be a list of tuples:
            hex string color definitions, and float values that are weights for
            random selection.
        """
        raise NotImplementedError()

    def presets(self):
        """
        The sub-class' presets attribute should be a dictionary of names and
        hex strings.
        """
        pass

    def get_color(self, name):
        name = name.strip().lower()
        if name in self.presets:
            return self.presets[name.strip().lower()]
        # sys.stdout.write(pprint.pformat(self._past_assignments)+"\n\n\n")
        color = None
        if name in self._past_assignments:
            for candidate in self._past_assignments[name]:
                available = [n[0] for n in self.available_colors]
                if candidate in available:
                    color = candidate
                    weight = dict(self.available_colors)[color]
                    self.available_colors.remove((color, weight))
                    break
        if color is None and self.available_colors:
            weights_sum = sum([n[1] for n in self.available_colors])
            roll = random.random() * weights_sum
            count = 0
            for color, weight in self.available_colors:
                count += weight
                if roll < count:
                    break
            self.available_colors.remove((color, weight))
            if name not in self._past_assignments:
                self._past_assignments[name] = []
            self._past_assignments[name].append(color)
        if color is None:
            color = '#000000'
        return color


class TangoPalette(BasePalette):

    def __init__(self):
        app = (widgets.QApplication.instance()
               or widgets.QApplication(sys.argv))
        bg_value = app.palette().color(gui.QPalette.Base).valueF()
        if bg_value < 33:
            dark = 20.0
            medium = 5.0
            light = 1.0
        elif bg_value < 66:
            dark = 5.0
            medium = 20.0
            light = 1.0
        else:
            dark = 5.0
            medium = 1.0
            light = 20.0
        self.colors = [
            ('#fce94f', light),  # Butter1
            ('#fcaf3e', light),  # Orange1
            ('#e9b96e', light),  # Chocolate1
            ('#8ae234', light),  # Chameleon1
            ('#729fcf', light),  # Sky Blue1
            ('#ad7fa8', light),  # Plum1
            ('#ef2929', light),  # Scarlet Red1
            ('#c4a000', dark),  # Butter3
            ('#ce5c00', dark),  # Orange3
            ('#8f5902', dark),  # Chocolate3
            ('#4e9a06', dark),  # Chameleon3
            ('#204a87', dark),  # Sky Blue3
            ('#5c3566', dark),  # Plum3
            ('#a40000', dark),  # Scarlet Red3
            ('#edd400', medium),  # Butter2
            ('#f57900', medium),  # Orange2
            ('#c17d11', medium),  # Chocolate2
            ('#73d216', medium),  # Chameleon2
            ('#3465a4', medium),  # Sky Blue2
            ('#75507b', medium),  # Plum2
            ('#cc0000', medium),  # Scarlet Red2
            # '#eeeeec', # Aluminium1
            # '#d3d7cf', # Aluminium2
            # '#babdb6', # Aluminium3
            # '#888a85', # Aluminium4
            # '#555753', # Aluminium5
            # '#2e3436', # Aluminium6
        ]
        self.presets = {
            'unrecorded': '#888a85',
            'other': '#555753',
        }
        super(TangoPalette, self).__init__()


def get_application_palette():
    # TODO: Interact with the application settings, when they exist.
    app = widgets.QApplication.instance()
    current = app.property('current_palette')
    if current is None:
        current = TangoPalette()
        app.setProperty('current_palette', current)
    else:
        current.refresh()
    return current
