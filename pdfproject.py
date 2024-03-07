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

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel,
                             QVBoxLayout, QHBoxLayout, QPushButton,
                             QSplitter, QFileDialog, QGroupBox,
                             QListWidgetItem, QListWidget, QFrame, QListView, QSlider)
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QRegion, QImage
from PyQt5.QtCore import (Qt, QRect, QPoint, pyqtSignal, QModelIndex, QTimer)
import math
import popplerqt5
import xml.etree.ElementTree as ET
import numpy as np
import cv2 as cv
import threading

#import pikepdf #TODO #used only to get pdf userunits if someday I need to read it...
usage = """
Load a PDF and display the first page.

Usage:

    python pdfproject.py file.pdf
"""


class AppPDFProjector(QWidget):
    def __init__(self, viewer_screen, projector_screen, argsv):
        super().__init__()

        #A timer to auto clear layer selection
        self.timerLayerSelClear = QTimer(self)
        self.timerLayerSelClear.setSingleShot(True)
        self.timerLayerSelClear.timeout.connect(self.timer_clear_layer_sel)

        # A timer to delay the rendering
        self.timerDelayRender = QTimer()
        self.timerDelayRender.setSingleShot(True)
        self.timerDelayRender.timeout.connect(self.timer_delay_render)
        self.bResetOffsetRotation = False

        # A timer to delay the HSV effects
        self.timerDelayHSVRedraw = QTimer()
        self.timerDelayHSVRedraw.setSingleShot(False)
        self.timerDelayHSVRedraw.timeout.connect(self.timer_delay_hsvredraw)
        self.timerDelayHSVRedraw.start(10)
        self.bRedrawHSVImage = False
        self.threadHSVRecompute = threading.Thread(target=self.thread_hsvRecompute)
        self.mutexHSV = threading.Lock()
        self.bForceHSVCalculation = False

        # read xml config
        script_directory = os.path.dirname(os.path.abspath(sys.argv[0]))
        tree = ET.parse(os.path.join(script_directory, 'config.xml'))
        root = tree.getroot()
        self.pdf_filename = ''
        self.title = 'PDF Projector'
        self.left = 10
        self.top = 10
        self.width = 1280
        self.height = 800
        self.pdfdoc = None
        initImg = QPixmap(self.width, self.height)
        initImg.fill(Qt.gray)
        self.pdfImage = initImg.toImage() #This is the displayed image
        self.pdfHSVimg = None #This is the pdf rendered to an opencv HSV image
        self.Hue_offset_current = 0 #Hue rotation angle from 0 to 179
        self.Hue_offset_target = 0  # Hue rotation angle from 0 to 179
        self.Sat_mult_current = 1  # Saturation multiplier
        self.Sat_mult_target = 1 #Saturation multiplier
        self.Val_mult_current = 1  # Value multiplier
        self.Val_mult_target = 1 #Value multiplier
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
        self.projectorPreview = PreviewPaintWidget(self.projectorWidth, self.projectorHeigth, self.pdfImage)
        self.projectorWindow = ProjectorWidget(self.projectorScreen, self.projectorWidth,
                                               self.projectorHeigth, self.fullscreenmode, self.pdfImage)
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

        #Mirror btn
        self.BtnMirror = QPushButton('Mirror')
        self.BtnMirror.setCheckable(True)
        self.hboxtopbuttons.addWidget(self.BtnMirror)
        self.BtnMirror.clicked.connect(self.mirror_btn_clicked)

        #Color effects
        self.frmColorEffects = QGroupBox()
        self.frmColorEffects.setTitle('Color Effects')
        self.hboxcoloreffects = QHBoxLayout()
        self.frmColorEffects.setLayout(self.hboxcoloreffects)
        self.btnResetHSV = QPushButton('Reset')
        self.hboxcoloreffects.addWidget(self.btnResetHSV)
        self.btnResetHSV.clicked.connect(self.btn_reset_hsv_clicked)
        self.hboxcoloreffects.addWidget(QLabel('Hue'))
        self.sliderHue = QSlider(Qt.Horizontal)
        self.hboxcoloreffects.addWidget(self.sliderHue)
        self.hboxcoloreffects.addWidget(QLabel('Saturation'))
        self.sliderSaturation = QSlider(Qt.Horizontal)
        self.hboxcoloreffects.addWidget(self.sliderSaturation)
        self.hboxcoloreffects.addWidget(QLabel('Light'))
        self.sliderValue = QSlider(Qt.Horizontal)
        self.hboxcoloreffects.addWidget(self.sliderValue)
        self.hboxtopbuttons.addWidget(self.frmColorEffects)
        self.frmColorEffects.setMaximumHeight(80)
        self.sliderHue.setRange(0, 179)
        self.sliderHue.setValue(0)
        self.sliderSaturation.setRange(-100,100)
        self.sliderSaturation.setValue(0)
        self.sliderValue.setRange(-100, 100)
        self.sliderValue.setValue(0)

        self.sliderHue.valueChanged.connect(self.slider_coloreffect_changed)
        self.sliderSaturation.valueChanged.connect(self.slider_coloreffect_changed)
        self.sliderValue.valueChanged.connect(self.slider_coloreffect_changed)

        self.BtnInvertColors = QPushButton('Invert Colors')
        self.BtnInvertColors.setCheckable(True)
        self.hboxcoloreffects.addWidget(self.BtnInvertColors)
        self.BtnInvertColors.clicked.connect(self.invertcolors_btn_clicked)

        if len(self.argsv) > 1: self.pdf_filename = self.argsv[-1]

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
        self.VBoxLeftPanel.addWidget(self.frmLayers)

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
        self.listview_pdflayers = QListView()
        self.listview_pdflayers.setLineWidth(0)
        self.listview_pdflayers.setFixedWidth(int(0.15 * self.width))
        self.layersLayout.addWidget(self.listview_pdflayers)

        # Load PDF file
        if len(self.pdf_filename) > 0:
            self.openPDF()
            self.pdfLoadPage2Qimage(True)
            self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(0)).setSelected(True)

        self.VBoxPageSplitter.addWidget(self.projectorPreview)
        self.VBoxPageSplitter.setCollapsible(1, False)
        self.projectorPreview.move(0, 0)
        self.projectorPreview.resize(self.pdfImage.width(), self.pdfImage.height())
        self.projectorPreview.sgn_rotation_offset_changed.connect(self.offset_rotation_changed)
        self.show()

        self.projectorWindow.setWindowTitle("Projector Window")
        self.projectorWindow.show()
    def layer_data_changed(self):
        self.pdfLoadPage2Qimage(False)
    def layer_selection_changed(self):
        self.timerLayerSelClear.start(1)  # Exec a timer to clear selection asap
    def timer_clear_layer_sel(self):
        self.listview_pdflayers.selectionModel().clearSelection()

    def btn_reset_hsv_clicked(self):
        self.sliderHue.setValue(0)
        self.sliderSaturation.setValue(1)
        self.sliderValue.setValue(1)
    def slider_coloreffect_changed(self):
        self.Hue_offset_target = self.sliderHue.value()
        self.Sat_mult_target = 10 * math.fabs(self.sliderSaturation.value()) / 100 + 1
        if self.sliderSaturation.value() < 0 : self.Sat_mult_target = 1 / self.Sat_mult_target
        self.Val_mult_target = 10 * math.fabs(self.sliderValue.value()) / 100 + 1
        if self.sliderValue.value() < 0: self.Val_mult_target  = 1 / self.Val_mult_target
        #The redraw is handled byt the hsv redraw timmer, nothing to do here

    def timer_delay_hsvredraw(self):
        if not self.threadHSVRecompute.is_alive():
            if self.bRedrawHSVImage:
                self.bForceHSVCalculation = False
                self.bRedrawHSVImage = False
                self.threadHSVRecompute.join()
                self.mutexHSV.acquire()
                self.projectorPreview.setPdfImage(self.pdfImage)
                self.projectorWindow.setPdfImage(self.pdfImage)
                self.mutexHSV.release()
            if (((self.Hue_offset_current != self.Hue_offset_target) or
                    (self.Sat_mult_current != self.Sat_mult_target) or
                    (self.Val_mult_current != self.Val_mult_target)) or
                    self.bForceHSVCalculation):
                self.threadHSVRecompute = threading.Thread(target=self.thread_hsvRecompute)
                self.threadHSVRecompute.start()

    def thread_hsvRecompute(self):
        self.bRedrawHSVImage = True
        if self.pdfHSVimg is not None:
            hueoffset = self.Hue_offset_target
            satmult = self.Sat_mult_target
            valmult = self.Val_mult_target
            arr = self.pdfHSVimg.copy()
            arr[:, :, 0] = arr[:, :, 0] + hueoffset
            arr[arr[:, :, 0] > 180, 0] = arr[arr[:, :, 0] > 180, 0] - 180
            arr[:, :, 1] = arr[:, :, 1] * satmult
            arr[arr[:, :, 1] > 255, 1] = 255
            arr[:, :, 2] = arr[:, :, 2] * valmult
            arr[arr[:, :, 2] > 255, 2] = 255
            arr = np.uint8(arr)
            arr = cv.cvtColor(arr, cv.COLOR_HSV2BGR)
            alphaChannel = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=np.uint8)
            arr = np.concatenate((arr, alphaChannel), axis=2)

            self.mutexHSV.acquire()
            self.pdfImage = QImage(arr.tobytes(), arr.shape[1], arr.shape[0], QImage.Format_ARGB32)
            self.mutexHSV.release()

            self.Hue_offset_current = hueoffset
            self.Sat_mult_current = satmult
            self.Val_mult_current = valmult


    def openPDF(self):
        #Load thumnails
        self.pdfdoc = popplerqt5.Poppler.Document.load(self.pdf_filename)
        self.pdfdoc.setRenderHint(popplerqt5.Poppler.Document.Antialiasing)
        self.pdfdoc.setRenderHint(popplerqt5.Poppler.Document.TextAntialiasing)

        if self.pdfdoc.hasOptionalContent():
            self.listview_pdflayers.setModel(self.pdfdoc.optionalContentModel())
            self.listview_pdflayers.setRootIndex(QModelIndex())
            self.listview_pdflayers.model().dataChanged.connect(self.layer_data_changed)
            self.listview_pdflayers.clicked.connect(self.layer_selection_changed) #using this trick to not allow selecting any item

        numpages = self.pdfdoc.numPages()
        self.listview_pdfpages.clear()
        for i in range(0, numpages):
            #unitPDF = self.getPdfUserUnits(i) #TODO disabled since most pdf files are not using it and it is not supported by poppler
            pageImg = self.pdfdoc.page(i)
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
        self.projectorWindow.setInvertColors(self.BtnInvertColors.isChecked())
    def mirror_btn_clicked(self):
        self.projectorPreview.setMirror(self.BtnMirror.isChecked())
        self.projectorWindow.setMirror(self.BtnMirror.isChecked())
    def closeEvent(self, event):
        if self.threadHSVRecompute.is_alive():
            self.threadHSVRecompute.join()
        self.projectorWindow.setCloseFlag()
        self.projectorWindow.close()
        event.accept()

    def pdfLoadPage2Qimage(self, ResetOffsetRotation):
        self.setCursor(Qt.WaitCursor)
        self.projectorPreview.setCursor(Qt.WaitCursor)
        self.bResetOffsetRotation = ResetOffsetRotation
        self.timerDelayRender.start(1)

    def timer_delay_render(self):
        # Loads the rendered pdf page to a global image var
        pageImg = self.pdfdoc.page(self.pdf_page_idex)

        self.mutexHSV.acquire()
        self.pdfImage = pageImg.renderToImage(self.projectorDPI, self.projectorDPI)
        self.mutexHSV.release()

        rawImg = self.pdfImage.convertToFormat(QImage.Format_ARGB32)
        ptr = rawImg.constBits()
        ptr.setsize(rawImg.height() * rawImg.width() * rawImg.depth() // 8)
        self.pdfHSVimg = np.ndarray(shape=(rawImg.height(), rawImg.width(), rawImg.depth() // 8), buffer=ptr, dtype=np.uint8)
        self.pdfHSVimg = self.pdfHSVimg[:, :, 0:3]  # Discard alpha channel, the image is reversed so the actual format is BGRA
        self.pdfHSVimg = cv.cvtColor(self.pdfHSVimg, cv.COLOR_BGR2HSV)
        self.pdfHSVimg = np.float32(self.pdfHSVimg)
        self.bForceHSVCalculation = True #Force redraw in the next cycle

        if self.bResetOffsetRotation:
            self.projectorWindow.setOffsetRotation(int(self.pdfImage.width() / 2), int(self.pdfImage.height() / 2), 0)
            self.projectorPreview.setScale(min(self.projectorPreview.width() / self.pdfImage.width(),
                                               self.projectorPreview.height() / self.pdfImage.height()))
            self.projectorPreview.setRotation(0)
            self.projectorPreview.setOffset(int(self.pdfImage.width() / 2), int(self.pdfImage.height() / 2))

        # Preload page image to widgets since the HSV processing take long time...
        self.mutexHSV.acquire()
        self.projectorPreview.setPdfImage(self.pdfImage)
        self.projectorWindow.setPdfImage(self.pdfImage)
        self.mutexHSV.release()
        self.setCursor(Qt.ArrowCursor)
        self.projectorPreview.setCursor(Qt.OpenHandCursor)

    def open_btn_clicked(self):
        pdffileName, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                  "PDF Files (*.pdf)")
        if pdffileName:
            self.pdf_filename = pdffileName
            self.pdf_page_idex = 0
            self.openPDF()
            self.pdfLoadPage2Qimage(True)
            self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(0)).setSelected(True)
    def list_pages_clicked(self, item):
       idx = self.listview_pdfpages.indexFromItem(item).row()

       for i in range(0, self.listview_pdfpages.count()):
           self.listview_pdfpages.itemWidget(self.listview_pdfpages.item(i)).setSelected(False)

       self.listview_pdfpages.itemWidget(item).setSelected(True)
       if idx != self.pdf_page_idex:
            self.pdf_page_idex = idx
            self.pdfLoadPage2Qimage(True)
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

    def __init__(self, projectoWidth, projectorHeight, pdf_image):
        self.dragModeIsRotation = False
        self.prev_xevent = 0
        self.prev_yevent = 0
        self.rotation = 0.0
        self.scale = 0.5
        self.bMirror = False
        self.bSlowMode = False
        self.xoffset = 0
        self.yoffset = 0
        self.projectorWidth = projectoWidth
        self.projectorHeight = projectorHeight
        self.img = pdf_image
        super().__init__()
        self.setCursor(Qt.OpenHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def setPdfImage(self, pdf_image):
        self.img = pdf_image
        self.repaint()
    def setMirror(self, bMirror):
        self.bMirror = bMirror
        self.repaint()
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
        self.setCursor(Qt.ClosedHandCursor)
    def mouseReleaseEvent(self, event):
        self.setMouseTracking(False)
        if self.bSlowMode:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
    def mouseMoveEvent(self, event):
        xdiff = event.x() - self.prev_xevent
        ydiff = event.y() - self.prev_yevent
        #print(f"Mouse DIFF: ({xdiff}, {ydiff})")
        if self.dragModeIsRotation:
            if self.bSlowMode:
                self.prev_xevent = event.x()
                self.prev_yevent = event.y()
                self.setRotation(self.rotation-ydiff*0.2)
            else:
                angle = math.floor(self.rotation/45) * 45
                if ydiff > 50:
                    angle = angle + 45
                    self.prev_xevent = event.x()
                    self.prev_yevent = event.y()
                elif ydiff < -50:
                    angle = angle - 45
                    self.prev_xevent = event.x()
                    self.prev_yevent = event.y()
                self.setRotation(angle)
        else:
            self.prev_xevent = event.x()
            self.prev_yevent = event.y()
            if self.bSlowMode:
                xdiff = 0.1 * xdiff
                ydiff = 0.1 * ydiff
            xdiffrotated = xdiff * math.cos(self.rotation * math.pi / 180) + ydiff * math.sin(self.rotation * math.pi / 180)
            ydiffrotated = -xdiff * math.sin(self.rotation * math.pi / 180) + ydiff * math.cos(self.rotation * math.pi / 180)
            self.setOffset(int((self.xoffset - xdiffrotated / self.scale)), int((self.yoffset - ydiffrotated / self.scale)))
    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.setScale(self.scale * 1.2)
        elif event.angleDelta().y() < 0:
            self.setScale(self.scale * 0.8)
        #print(f"Wheel delta: ({event.angleDelta().y()})")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = True
            self.setCursor(Qt.PointingHandCursor)
    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = False
            self.setCursor(Qt.OpenHandCursor)
    def focusOutEvent(self, e):
        self.bSlowMode = False
        self.setCursor(Qt.OpenHandCursor)
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
        qp.drawPixmap(-self.xoffset ,
                      -self.yoffset,
                      QPixmap.fromImage(self.img.mirrored(self.bMirror, False)))
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
    def __init__(self, projectorScreen, projectoWidth, projectorHeight, bfullscreen, pdf_img):
        self.xoffset = 0
        self.yoffset = 0
        self.rotation = 0
        self.binvertcolors = False
        self.bMirror = False
        self.bclose = False
        super().__init__()
        qr = projectorScreen.geometry()
        self.move(qr.left(), qr.top())
        self.setFixedWidth(projectoWidth)
        self.setFixedHeight(projectorHeight)
        self.img = pdf_img
        if bfullscreen:
            self.showFullScreen()
    def setPdfImage(self, pdf_image):
        self.img = pdf_image
        self.repaint()
    def setOffsetRotation(self, xoff, yoff, angle):
        self.xoffset = xoff
        self.yoffset = yoff
        self.rotation = angle
        self.repaint()
    def setMirror(self, bMirror):
        self.bMirror = bMirror
        self.repaint()
    def setInvertColors(self, bInvert):
        self.binvertcolors = bInvert
        self.repaint()
    def setCloseFlag(self):
        self.bclose = True
    def closeEvent(self, event):
        if self.bclose:
            event.accept()
        else:
            event.ignore()
    def paintEvent(self, event):
        plotraster = self.img.mirrored(self.bMirror, False).copy()

        if self.binvertcolors:
            plotraster.invertPixels()  #TODO consider inverting colors at both widgets... is this useful?

        qp = QPainter(self)
        viewArea = QRect(0, 0, self.width(), self.height())
        viewAreaCenter = viewArea.center()

        # Paint background
        qp.save()
        if self.binvertcolors:
            qp.fillRect(viewArea, Qt.black)
        else:
            qp.fillRect(viewArea, Qt.white)
        qp.restore()

        qp.save()
        qp.translate(viewAreaCenter)
        qp.rotate(self.rotation)
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
