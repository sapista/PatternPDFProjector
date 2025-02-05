#########################################################################
#     PatternPDFProjector - PDF Viewer for sewing pattern projection
#     Copyright (C) 2024 Pere Rafols Soler
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
############################################################################

import os
import sys

from PyQt5.QtWidgets import QApplication
import main_win as ProjectorApp

usage = """
Load a PDF and display the first page.

Usage:

    python pdfproject.py file.pdf
"""

if __name__ == '__main__':
    app = QApplication(sys.argv)
    my_screens = app.screens()
    if len(my_screens) > 1:
        projectorScreen = my_screens[1]
    else:
        projectorScreen = my_screens[0]

    viewerScreen = my_screens[0]
    argv = QApplication.arguments()
    ex = ProjectorApp.AppPDFProjector(viewerScreen, projectorScreen, argv)
    sys.exit(app.exec_())
