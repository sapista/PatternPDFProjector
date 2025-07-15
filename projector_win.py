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

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPixmap, QImage
from PyQt5.QtCore import Qt, pyqtSignal
import numpy as np
import cv2 as cv
import py_compile

class ProjectorWindow(QWidget):
    mouse_move = pyqtSignal(float, float, bool, bool, bool) #xdelta, ydelta, leftbutton, rightbutton, slowmode
    arrow_key = pyqtSignal(object)
    def __init__(self, projectorScreen, projectorWidth, projectorHeight, bfullscreen, renderDPI, projectorXDPI, projectorYDPI):
        self.binvertcolors = False
        self.bclose = False
        self.prev_xevent = 0
        self.prev_yevent = 0
        self.bLeftButton = False
        self.bRightButton = False
        self.bSlowMode = False
        initImg = QPixmap(projectorWidth, projectorHeight)
        initImg.fill(Qt.gray)
        self.img = initImg.toImage()  # This is the displayed image
        self.xScaleFactor = projectorXDPI / renderDPI;
        self.yScaleFactor = projectorYDPI / renderDPI;
        super().__init__()
        qr = projectorScreen.geometry()
        self.move(qr.left(), qr.top())
        self.setFixedWidth(projectorWidth)
        self.setFixedHeight(projectorHeight)
        if bfullscreen:
            self.showFullScreen()
        erode_size = 3 #Must be odd to have a center in order to grow from the line center
        self.erode_ker = cv.getStructuringElement(cv.MORPH_ELLIPSE, (erode_size, erode_size)) #Works smoother using a circle
        self.setCursor(Qt.OpenHandCursor)

    def setCloseFlag(self):
        self.bclose = True

    def closeEvent(self, event):
        if self.bclose:
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        self.setMouseTracking(True)
        self.prev_xevent = event.x()
        self.prev_yevent = event.y()
        self.setCursor(Qt.ClosedHandCursor)
        if event.button() == Qt.LeftButton:
            self.bLeftButton = True
        elif event.button() == Qt.RightButton:
            self.bRightButton = True

    def mouseReleaseEvent(self, event):
        self.setMouseTracking(False)
        self.bLeftButton = False
        self.bRightButton = False
        if self.bSlowMode:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)

    def mouseMoveEvent(self, event):
        xdiff = event.x() - self.prev_xevent
        ydiff = event.y() - self.prev_yevent
        self.prev_xevent = event.x()
        self.prev_yevent = event.y()
        #print(f"Mouse DIFF: ({xdiff}, {ydiff})")
        xdiff = xdiff / self.xScaleFactor
        ydiff = ydiff / self.yScaleFactor
        self.mouse_move.emit(xdiff, ydiff, self.bLeftButton, self.bRightButton, self.bSlowMode)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = True
            self.setCursor(Qt.PointingHandCursor)
        if e.key() == Qt.Key_Up or e.key() == Qt.Key_Down or e.key() == Qt.Key_Left or e.key() == Qt.Key_Right:
            self.arrow_key.emit(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = False
            self.setCursor(Qt.OpenHandCursor)

    def redraw(self, newImg, bInvertColors, iLineGrow):
        self.binvertcolors = bInvertColors

        newImg = newImg.convertToFormat(QImage.Format_ARGB32)
        ptr = newImg.constBits()
        ptr.setsize(newImg.height() * newImg.width() * newImg.depth() // 8)
        arr_drwcvimg = np.ndarray(shape=(newImg.height(), newImg.width(), newImg.depth() // 8), buffer=ptr,
                                    dtype=np.uint8)

        if iLineGrow > 0:
            arr_drwcvimg = cv.erode(src=arr_drwcvimg, kernel=self.erode_ker, iterations=iLineGrow, anchor=(-1,-1),
                                    borderType=cv.BORDER_CONSTANT, borderValue = 1)

        self.img = QImage(arr_drwcvimg.tobytes(), arr_drwcvimg.shape[1], arr_drwcvimg.shape[0], QImage.Format_ARGB32)
        self.repaint()

    def paintEvent(self, event):
        if self.binvertcolors:
            self.img.invertPixels()
        qp = QPainter(self)
        qp.scale(self.xScaleFactor, self.yScaleFactor)
        qp.drawPixmap(0,0, QPixmap.fromImage(self.img))
