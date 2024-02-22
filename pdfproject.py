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

import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel,
                             QVBoxLayout, QHBoxLayout, QPushButton,
                             QSplitter, QFileDialog, QGroupBox,
                             QListWidgetItem, QListWidget, QFrame)
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QRegion
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import (Qt, QRect, QPoint, pyqtSignal)
import math
import popplerqt5
import xml.etree.ElementTree as ET
#import pikepdf #used only to get pdf userunits if someday I need to read it... #TODO
usage = """
Load a PDF and display the first page.

Usage:

    python pdfproject.py file.pdf
"""


class AppPDFProjector(QWidget):
    def __init__(self, viewer_screen, projector_screen, argsv):
        super().__init__()

        #read xml config
        tree = ET.parse('config.xml')
        root = tree.getroot()
        self.pdf_filename = ''
        self.title = 'PDF Projector'
        self.left = 10
        self.top = 10
        self.width = 1280
        self.height = 800
        global pdfImage
        initImg = QPixmap(self.width, self.height)
        initImg.fill(Qt.gray)
        pdfImage = initImg.toImage()
        self.projectorDPI = float(root.find('projector_dpi').text)
        self.fullscreenmode = root.find('fullscreen_mode').text.upper() == 'TRUE'
        if self.fullscreenmode:
            self.projectorWidth = projector_screen.size().width()
            self.projectorHeigth = projector_screen.size().height()
        else:
            self.projectorWidth = int(root.find('projector_width').text)
            self.projectorHeigth = int(root.find('projector_height').text)

        self.projectorScreen = projector_screen
        self.argsv = argsv
        self.pdf_page_idex = 0
        self.prjRender = PreviewPaintWidget(self.projectorWidth, self.projectorHeigth)
        self.projectorWindow = ProjectorWidget(self.projectorScreen, self.projectorWidth,
                                               self.projectorHeigth, self.fullscreenmode)
        self.initUI()
        qr = viewer_screen.geometry()
        self.move(qr.left(), qr.top())
        self.showMaximized()
    def initUI(self):

        self.vboxmain = QVBoxLayout()
        self.hboxtopbuttons = QHBoxLayout()
        self.BtnOpenPDF = QPushButton('Open PDF')
        self.hboxtopbuttons.addWidget(self.BtnOpenPDF)
        self.BtnOpenPDF.clicked.connect(self.open_btn_clicked)
        self.vboxmain.addLayout(self.hboxtopbuttons)
        self.setLayout(self.vboxmain)

        self.BtnInvertColors = QPushButton('Invert Colors')
        self.BtnInvertColors.setCheckable(True)
        self.hboxtopbuttons.addWidget(self.BtnInvertColors)
        self.BtnInvertColors.clicked.connect(self.invertcolors_btn_clicked)

        if len(self.argsv) > 1: self.pdf_filename = self.argsv[-1]
        #else: self.pdf_filename = '/home/sapista/build/PatternPDFProjector/testFiles/squaretest1500.pdf' #uncomment for faster debugging

        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.VBoxPageSplitter = QSplitter()
        self.vboxmain.addWidget(self.VBoxPageSplitter)

        #GroupBox for pages
        self.frmPages = QGroupBox()
        self.frmPages.setTitle('Pages')
        self.pagesLayout = QVBoxLayout()
        self.frmPages.setLayout(self.pagesLayout)

        #GroupBox for Layers
        self.frmLayers = QGroupBox()
        self.frmLayers.setTitle('Layers')
        self.layersLayout = QVBoxLayout()
        self.frmLayers.setLayout(self.layersLayout)

        self.VBoxLeftPanel = QVBoxLayout()
        self.VBoxLeftPanel.addWidget(self.frmPages)
        #self.VBoxLeftPanel.addWidget(self.frmLayers) #TODO ready to enable when layers are implemented

        self.LeftPanel = QFrame()
        self.LeftPanel.setLayout(self.VBoxLeftPanel)
        self.LeftPanel.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.LeftPanel.setLineWidth(0)
        self.VBoxPageSplitter.addWidget(self.LeftPanel)
        self.VBoxPageSplitter.setCollapsible(0, False)

        #List view for pages
        self.listview_pdfpages = QListWidget()
        self.listview_pdfpages.setLineWidth(0)
        self.listview_pdfpages.setFixedWidth(int(0.15*self.width))
        self.listview_pdfpages.itemClicked.connect(self.list_pages_clicked)
        self.pagesLayout.addWidget(self.listview_pdfpages)

        # List view for layers
        self.listview_pdflayers = QListWidget()
        self.listview_pdflayers.setLineWidth(0)
        self.listview_pdflayers.setFixedWidth(int(0.15 * self.width))
        self.listview_pdflayers.itemClicked.connect(self.list_layers_clicked)
        self.layersLayout.addWidget(self.listview_pdflayers)

        # Load PDF file
        if len(self.pdf_filename) > 0:
            self.openPDF()
            self.pdfLoadPage2Qimage()
            self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(0)).setSelected(True)

        self.VBoxPageSplitter.addWidget(self.prjRender)
        self.VBoxPageSplitter.setCollapsible(1, False)
        self.prjRender.move(0,0)
        self.prjRender.resize(pdfImage.width(),pdfImage.height())
        self.prjRender.sgn_rotation_offset_changed.connect(self.offset_rotation_changed)
        self.show()

        self.projectorWindow.setWindowTitle("Projector Window")
        self.projectorWindow.show()

    def openPDF(self):
        #Load thumnails
        doc = popplerqt5.Poppler.Document.load(self.pdf_filename)
        doc.setRenderHint(popplerqt5.Poppler.Document.Antialiasing)
        doc.setRenderHint(popplerqt5.Poppler.Document.TextAntialiasing)
        numpages = doc.numPages()

        self.listview_pdfpages.clear()
        for i in range(0, numpages):
            #unitPDF = self.getPdfUserUnits(i) #TODO disabled since most pdf files are not using it and it is not supported by poppler
            pageImg = doc.page(i)
            #pageWidthInch = pageImg.pageSizeF().width() * unitPDF #TODO disabled since most pdf files are not using it and it is not supported by poppler
            pageWidthInch = pageImg.pageSizeF().width() * 1/72
            thumnailDPI = 0.6*self.listview_pdfpages.width() / pageWidthInch
            pImg = pageImg.renderToImage(thumnailDPI, thumnailDPI)
            myPageThumb = pdfPagePreviewWidget()
            myPageThumb.setPageNumberText(i+1)
            myPageThumb.setPDFImage(pImg)
            myQListWidgetItem = QListWidgetItem(self.listview_pdfpages)
            # Set size hint
            myQListWidgetItem.setSizeHint(myPageThumb.sizeHint())
            # Add QListWidgetItem into QListWidget
            self.listview_pdfpages.addItem(myQListWidgetItem)
            self.listview_pdfpages.setItemWidget(myQListWidgetItem, myPageThumb)

    #TODO method to get userunit for PDF files not using the standard dot size of 1/72 inch
    """
    def getPdfUserUnits(self, page):
        # Get User units using pikepdf
        pdf = pikepdf.Pdf.open(self.pdf_filename)
        page = pdf.pages[page]
        userunit = 1/72
        if '/UserUnit' in page:
            userunit = 1/float(page.UserUnit)
            #TODO im getting the user unit right...but I dont know how to use it... im currently no usiung it to scale the projector display

        return userunit
    """
    def invertcolors_btn_clicked(self):
        self.projectorWindow.setIvertColors(self.BtnInvertColors.isChecked())
    def closeEvent(self, event):
        self.projectorWindow.setCloseFlag()
        self.projectorWindow.close()
        event.accept()

    def pdfLoadPage2Qimage(self):
        # Loads the rendered pdf page to a global image var
        doc = popplerqt5.Poppler.Document.load(self.pdf_filename)
        doc.setRenderHint(popplerqt5.Poppler.Document.Antialiasing)
        doc.setRenderHint(popplerqt5.Poppler.Document.TextAntialiasing)
        pageImg = doc.page(self.pdf_page_idex)

        global pdfImage
        pdfImage = pageImg.renderToImage(self.projectorDPI, self.projectorDPI)
        self.projectorWindow.setOffsetRotation(int(pdfImage.width()/2), int(pdfImage.height()/2), 0)
        self.prjRender.setScale(min(self.prjRender.width()/pdfImage.width(), self.prjRender.height()/pdfImage.height()))
        self.prjRender.setRotation(0)
        self.prjRender.setOffset(int(pdfImage.width()/2), int(pdfImage.height()/2))
        self.repaint()
        self.projectorWindow.repaint()

    def open_btn_clicked(self):
        pdffileName, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                  "PDF Files (*.pdf)")
        if pdffileName:
            self.pdf_filename = pdffileName
            self.pdf_page_idex = 0
            self.openPDF()
            self.pdfLoadPage2Qimage()
            self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(0)).setSelected(True)
    def list_pages_clicked(self, item):
       idx = self.listview_pdfpages.indexFromItem(item).row()

       for i in range(0, self.listview_pdfpages.count()):
           self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(i)).setSelected(False)

       self.listview_pdfpages.itemWidget(item).setSelected(True)
       if idx != self.pdf_page_idex:
            self.pdf_page_idex = idx
            self.pdfLoadPage2Qimage()

    def list_layers_clicked(self, item):
        idx = self.listview_pdflayers.indexFromItem(item).row()
        print(idx)
        #TODO implement me!
    def offset_rotation_changed(self, xoff, yoff, rot):
        self.projectorWindow.setOffsetRotation(xoff, yoff, rot)

class pdfPagePreviewWidget(QFrame):
    def __init__(self, parent=None):
        super(pdfPagePreviewWidget, self).__init__(parent)
        self.VBox = QVBoxLayout()
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(0)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet('background-color: gray;')

        self.lblpageimage = QLabel()
        self.lblpagenumber = QLabel()
        self.lblpagenumber.setAlignment(Qt.AlignCenter)
        self.lblpageimage.setAlignment(Qt.AlignCenter)
        self.VBox.addWidget(self.lblpageimage)
        self.VBox.addWidget(self.lblpagenumber)
        self.setLayout(self.VBox)

    def setPageNumberText (self, pagenumber):
        self.lblpagenumber.setText(str(pagenumber))

    def setPDFImage (self, pdfimg):
        self.lblpageimage.setPixmap(QPixmap.fromImage(pdfimg))

    def setSelected (self, sel):
        if sel:
            self.setStyleSheet('background-color: rgba(0, 50, 50, 150);')
        else:
            self.setStyleSheet('background-color: gray;')

class PreviewPaintWidget(QWidget):
    sgn_rotation_offset_changed = pyqtSignal(int, int, float)

    def __init__(self, projectoWidth, projectorHeight):
        self.dragModeIsRotation = False
        self.prev_xevent = 0
        self.prev_yevent = 0
        self.rotation = 0.0
        self.scale = 0.5
        self.xoffset = 0
        self.yoffset = 0
        self.projectorWidth = projectoWidth
        self.projectorHeight = projectorHeight
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)

    def setRotation(self, angle):
        self.rotation = angle
        self.repaint()
        self.sgn_rotation_offset_changed.emit(self.xoffset, self.yoffset, self.rotation)

    def setOffset(self, xoff, yoff):
        self.xoffset = xoff
        self.yoffset = yoff
        self.repaint()
        self.sgn_rotation_offset_changed.emit(self.xoffset, self.yoffset, self.rotation)

    def setScale(self, scale):
        max_scale_w = self.width() / self.projectorWidth
        max_scale_h = self.height() / self.projectorHeight
        max_scale = min(max_scale_w, max_scale_h)
        if scale > max_scale:
            scale = max_scale
        self.scale = scale
        self.repaint()

    def mousePressEvent(self, event):
        self.setMouseTracking(True)
        self.prev_xevent = event.x()
        self.prev_yevent = event.y()
        # Override the mousePressEvent to customize behavior
        if event.button() == Qt.LeftButton:
            self.dragModeIsRotation = False
        elif event.button() == Qt.RightButton:
            self.dragModeIsRotation = True

    def mouseReleaseEvent(self, event):
        self.setMouseTracking(False)

    def mouseMoveEvent(self, event):
        xdiff = event.x() - self.prev_xevent
        ydiff = event.y() - self.prev_yevent
        self.prev_xevent = event.x()
        self.prev_yevent = event.y()
        #print(f"Mouse DIFF: ({xdiff}, {ydiff})")
        if self.dragModeIsRotation:
            self.setRotation(self.rotation-ydiff*0.2)
        else:
            xdiffrotated = xdiff * math.cos(self.rotation * math.pi / 180) + ydiff * math.sin(self.rotation * math.pi / 180)
            ydiffrotated = -xdiff * math.sin(self.rotation * math.pi / 180) + ydiff * math.cos(self.rotation * math.pi / 180)
            self.setOffset(int((self.xoffset - xdiffrotated / self.scale)), int((self.yoffset - ydiffrotated / self.scale)))
    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.setScale(self.scale * 1.2)
        elif event.angleDelta().y() < 0:
            self.setScale(self.scale * 0.8)
        #print(f"Wheel delta: ({event.angleDelta().y()})")

    def paintEvent(self, event):
        qp = QPainter(self)

        viewArea = QRect(0, 0, self.width(), self.height())
        viewAreaCenter = viewArea.center()
        winProjector = QRect(0, 0, int(self.projectorWidth*self.scale), int(self.projectorHeight*self.scale))

        qp.save()
        qp.fillRect(viewArea, Qt.gray)
        qp.restore()

        #Draw PDF render
        qp.save()
        qp.translate(viewAreaCenter)
        qp.rotate(self.rotation)
        qp.scale(self.scale, self.scale)
        qp.drawPixmap(-self.xoffset, -self.yoffset, QPixmap.fromImage(pdfImage))
        qp.restore()

        #Display projection area
        qp.save()
        qp.translate(viewAreaCenter)
        winProjector.moveCenter(QPoint(0, 0))
        viewArea.moveCenter(QPoint(0, 0))
        pen = QPen(QColor(3, 252, 227))
        pen.setWidth(3)
        qp.setPen(pen)
        qp.drawRect(winProjector)
        outsidProjector = QRegion(viewArea, QRegion.Rectangle)
        insideProjector = QRegion(winProjector, QRegion.Rectangle)
        grayArea = outsidProjector.subtracted(insideProjector)
        qp.setClipRegion(grayArea)
        qp.fillRect(viewArea, QColor(3, 252, 227, 80))
        qp.restore()

class ProjectorWidget(QWidget):
    def __init__(self, projectorScreen, projectoWidth, projectorHeight, bfullscreen):
        self.xoffset = 0
        self.yoffset = 0
        self.rotation = 0
        self.binvertcolors = False
        self.bclose = False
        super().__init__()
        qr = projectorScreen.geometry()
        self.move(qr.left(), qr.top())
        self.setFixedWidth(projectoWidth)
        self.setFixedHeight(projectorHeight)
        if bfullscreen:
            self.showFullScreen()
    def setOffsetRotation(self, xoff, yoff, angle):
        self.xoffset = xoff
        self.yoffset = yoff
        self.rotation = angle
        self.repaint()

    def setIvertColors(self, invert):
        self.binvertcolors = invert
        self.repaint()

    def setCloseFlag(self):
        self.bclose = True
    def closeEvent(self, event):
        if self.bclose:
            event.accept()
        else:
            event.ignore()
    def paintEvent(self, event):
        #The commeted method does the same but working in a smaller region. However, it does not play well with rotation
        #plotraster = pdfImage.copy(int(self.xoffset-self.width()/2), int(self.yoffset-self.height()/2),
        #                           self.width(), self.height())
        plotraster = pdfImage.copy()
        if self.binvertcolors:
            plotraster.invertPixels()

        qp = QPainter(self)
        viewArea = QRect(0, 0, self.width(), self.height())
        viewAreaCenter = viewArea.center()
        qp.save()
        qp.translate(viewAreaCenter)
        qp.rotate(self.rotation)
        # The commeted method does the same but working in a smaller region. However, it does not play well with rotation
        #qp.drawPixmap(-int(self.width()/2), -int(self.height()/2), QPixmap.fromImage(plotraster))
        qp.drawPixmap(-self.xoffset, -self.yoffset, QPixmap.fromImage(plotraster))
        qp.restore()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    my_screens = app.screens()
    if len(my_screens) > 1:
        projectorScreen = my_screens[1]
    else:
        projectorScreen = my_screens[0]

    viewerScreen = my_screens[0]
    argv = QApplication.arguments()
    ex = AppPDFProjector(viewerScreen, projectorScreen, argv)
    sys.exit(app.exec_())