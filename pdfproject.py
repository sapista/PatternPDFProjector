import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel,
                             QVBoxLayout, QHBoxLayout, QPushButton,
                             QSplitter, QSlider, QFileDialog,
                             QListWidgetItem, QListWidget, QFrame)
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QRegion
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import (Qt, QRect, QPoint, pyqtSignal)
import math
import popplerqt5
import xml.etree.ElementTree as ET

usage = """
Demo to load a PDF and display the first page.

Usage:

    python pdfproject.py file.pdf
"""


class AppPDFProjector(QWidget):
    def __init__(self, viewer_screen, projector_screen, argsv):
        super().__init__()

        #read xml config
        tree = ET.parse('config.xml')
        root = tree.getroot()

        self.title = 'PDF Projector'
        self.left = 10
        self.top = 10
        self.width = 1280
        self.height = 800
        self.projectorWidth = int(root.find('projector_width').text)
        self.projectorHeigth = int(root.find('projector_height').text)
        self.projectorDPI = float(root.find('projector_dpi').text)
        self.fullscreenmode = bool(root.find('fullscreen_mode').text) #TODO use this!
        self.projectorScreen = projector_screen
        self.argsv = argsv
        self.pdf_page_idex = 0
        self.prjRender = PreviewPaintWidget(self.projectorWidth, self.projectorHeigth)
        self.projectorWindow = ProjectorWidget(self.projectorScreen, self.projectorWidth,
                                               self.projectorHeigth)  # TODO there is no need to convey width and heigh if projector screen?
        self.initUI()
        qr = viewer_screen.geometry()
        self.move(qr.left(), qr.top())

    def initUI(self):

        self.vboxmain = QVBoxLayout()
        self.hboxtopbuttons = QHBoxLayout()
        self.BtnOpenPDF = QPushButton('Open PDF') #TODO maybe add an icon?
        self.hboxtopbuttons.addWidget(self.BtnOpenPDF)
        self.BtnOpenPDF.clicked.connect(self.open_btn_clicked)
        self.vboxmain.addLayout(self.hboxtopbuttons)
        self.setLayout(self.vboxmain)

        #TODO add a view reset buttom

        if len(self.argsv) < 2:
            # sys.stderr.write(usage)
            # sys.exit(2)
            self.pdf_filename = '/home/sapista/build/PatternPDFProjector/testFiles/squaretest1500.pdf'
            #TODO just open the file selector?
        else:
            self.pdf_filename = self.argsv[-1]

        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height) #TODO investigate what are doing left and right

        self.VBoxPageSplitter = QSplitter()
        self.vboxmain.addWidget(self.VBoxPageSplitter)
        self.listview_pdfpages = QListWidget()
        self.listview_pdfpages.setFixedWidth(int(0.1*self.width))
        self.listview_pdfpages.itemClicked.connect(self.list_pages_clicked)
        self.VBoxPageSplitter.addWidget(self.listview_pdfpages)
        self.VBoxPageSplitter.setCollapsible(0, False)

        # Set window background color
        #self.setAutoFillBackground(True)
        #p = self.palette()
        #p.setColor(self.backgroundRole(), Qt.white)
        #self.setPalette(p)

        # Load PDF file
        # TODO emptu file? work on not loading anything, let the app to be just empty
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
            pageImg = doc.page(i)
            pageWidthInch = pageImg.pageSizeF().width() / 72
            thumnailDPI = 0.6 * self.listview_pdfpages.width() / pageWidthInch
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

    def closeEvent(self, event):
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
    def offset_rotation_changed(self, xoff, yoff, rot):
        self.projectorWindow.setOffsetRotation(xoff, yoff, rot)

class pdfPagePreviewWidget(QFrame):
    def __init__(self, parent=None):
        super(pdfPagePreviewWidget, self).__init__(parent)
        self.VBox = QVBoxLayout()
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(2)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet('background-color: gray;')

        self.lblpageimage = QLabel()
        self.lblpagenumber = QLabel()
        self.lblpagenumber.setAlignment(Qt.AlignCenter)
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
        self.xoffset = 0 #TODO es pot millorar posantlo al centre del Qimage: pdfImage.width()/2 xo img encara no hi es
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
            self.setOffset(self.xoffset-xdiff, self.yoffset-ydiff)

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.setScale(self.scale * 1.01)
        elif event.angleDelta().y() < 0:
            self.setScale(self.scale * 0.99)
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
    def __init__(self, projectorScreen, projectoWidth, projectorHeight):
        self.xoffset = 0
        self.yoffset = 0
        self.rotation = 0
        super().__init__()
        qr = projectorScreen.geometry()
        self.move(qr.left(), qr.top())
        self.resize(projectoWidth, projectorHeight)
#TODO set resizable False
    def setOffsetRotation(self, xoff, yoff, angle):
        self.xoffset = xoff
        self.yoffset = yoff
        self.rotation = angle
        self.repaint()

    def paintEvent(self, event):
        qp = QPainter(self)
        viewArea = QRect(0, 0, self.width(), self.height())
        viewAreaCenter = viewArea.center()
        qp.save()
        qp.translate(viewAreaCenter)
        qp.rotate(self.rotation)
        qp.drawPixmap(-self.xoffset, -self.yoffset, QPixmap.fromImage(pdfImage))
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