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

from PyQt5.QtWidgets import (QWidget, QLabel,
                             QVBoxLayout, QHBoxLayout, QPushButton,
                             QSplitter, QFileDialog, QGroupBox,
                             QListWidgetItem, QListWidget, QFrame, QListView, QSlider, QCheckBox, QMessageBox)
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QRegion, QImage
from PyQt5.QtCore import (Qt, QRect, QPoint, QModelIndex, QTimer)
import math
import popplerqt5
import xml.etree.ElementTree as ET
import numpy as np
import cv2 as cv
import threading
import pikepdf

import projector_win as prjWin

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
        self.projectorDPI = float(root.find('projector_dpi').text)
        self.fullscreenmode = root.find('fullscreen_mode').text.upper() == 'TRUE'
        if self.fullscreenmode:
            if projector_screen == viewer_screen:
                msgBox = QMessageBox()
                msgBox.setIcon(QMessageBox.Critical)
                msgBox.setText("No projector found! Exiting...")
                msgBox.setWindowTitle("No projector error")
                msgBox.setStandardButtons(QMessageBox.Ok)
                returnValue = msgBox.exec()
                if returnValue == QMessageBox.Ok:
                    sys.exit(1)

            self.projectorWidth = projector_screen.size().width()
            self.projectorHeigth = projector_screen.size().height()
        else:
            self.projectorWidth = int(root.find('projector_width').text)
            self.projectorHeigth = int(root.find('projector_height').text)

        self.projectorScreen = projector_screen
        self.argsv = argsv
        self.pdf_page_idex = 0
        self.projectorWidget = ProjectorPaintWidget(self.projectorWidth, self.projectorHeigth,
                                                    self.projectorScreen, self.fullscreenmode, self.projectorDPI)

        self.initUI()
        qr = viewer_screen.geometry()
        self.move(qr.left(), qr.top())
        if self.fullscreenmode:
            self.showMaximized()
        else:
            self.showNormal()

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
        self.hboxcoloreffects.addWidget(QLabel('Thickness'))
        self.sliderThickness = QSlider(Qt.Horizontal)
        self.hboxcoloreffects.addWidget(self.sliderThickness)
        self.hboxtopbuttons.addWidget(self.frmColorEffects)
        self.frmColorEffects.setMaximumHeight(80)
        self.sliderHue.setRange(0, 179)
        self.sliderHue.setValue(0)
        self.sliderSaturation.setRange(-100,100)
        self.sliderSaturation.setValue(0)
        self.sliderValue.setRange(-100, 100)
        self.sliderValue.setValue(0)
        self.sliderThickness.setRange(0,5)
        self.sliderThickness.setValue(0)

        self.sliderHue.valueChanged.connect(self.slider_coloreffect_changed)
        self.sliderSaturation.valueChanged.connect(self.slider_coloreffect_changed)
        self.sliderValue.valueChanged.connect(self.slider_coloreffect_changed)
        self.sliderThickness.valueChanged.connect(self.slider_thickness_changed)

        self.BtnInvertColors = QPushButton('Invert Colors')
        self.BtnInvertColors.setCheckable(True)
        self.hboxcoloreffects.addWidget(self.BtnInvertColors)
        self.BtnInvertColors.clicked.connect(self.invertcolors_btn_clicked)

        self.checkBoxInvertBoth = QCheckBox('Invert Both')
        self.hboxcoloreffects.addWidget(self.checkBoxInvertBoth)
        self.checkBoxInvertBoth.clicked.connect(self.invertcolors_btn_clicked)

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

        self.VBoxPageSplitter.addWidget(self.projectorWidget)
        self.VBoxPageSplitter.setCollapsible(1, False)
        self.projectorWidget.move(0, 0)

        self.show()
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
        sat = 10 * math.fabs(self.sliderSaturation.value()) / 100 + 1
        if self.sliderSaturation.value() < 0 : sat = 1 / sat
        val = 10 * math.fabs(self.sliderValue.value()) / 100 + 1
        if self.sliderValue.value() < 0: val = 1 / val
        self.projectorWidget.setHSVColorEffects(self.sliderHue.value(), sat, val)

    def slider_thickness_changed(self):
        self.projectorWidget.setThickness(self.sliderThickness.value())

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
            unitPDF = self.getPdfUserUnits(i)
            pageImg = self.pdfdoc.page(i)
            pageWidthInch = pageImg.pageSizeF().width() * unitPDF/72.0
            thumnailDPI = 0.6*self.listview_pdfpages.width() / pageWidthInch
            pImg = pageImg.renderToImage(thumnailDPI * unitPDF, thumnailDPI * unitPDF)
            myPageThumb = pdfPagePreviewWidget()
            myPageThumb.setPageNumberText(i+1)
            myPageThumb.setPDFImage(pImg)
            myQListWidgetItem = QListWidgetItem(self.listview_pdfpages)
            # Set size hint
            myQListWidgetItem.setSizeHint(myPageThumb.sizeHint())
            # Add QListWidgetItem into QListWidget
            self.listview_pdfpages.addItem(myQListWidgetItem)
            self.listview_pdfpages.setItemWidget(myQListWidgetItem, myPageThumb)

    # method to get userunit for PDF files not using the standard dot size of 1/72 inch
    def getPdfUserUnits(self, page):
        # Get User units using pikepdf
        pdf = pikepdf.Pdf.open(self.pdf_filename)
        page = pdf.pages[page]
        userunit = 1.0
        if '/UserUnit' in page:
            userunit = float(page.UserUnit)
        return userunit

    def invertcolors_btn_clicked(self):
        self.projectorWidget.setInvertColors(self.BtnInvertColors.isChecked(), self.BtnInvertColors.isChecked() and self.checkBoxInvertBoth.isChecked())

    def mirror_btn_clicked(self):
        self.projectorWidget.setMirror(self.BtnMirror.isChecked())

    def closeEvent(self, event):
        self.projectorWidget.close()
        event.accept()

    def pdfLoadPage2Qimage(self, ResetOffsetRotation):
        self.setCursor(Qt.WaitCursor)
        self.projectorWidget.setCursor(Qt.WaitCursor)
        self.bResetOffsetRotation = ResetOffsetRotation
        self.timerDelayRender.start(1)

    def timer_delay_render(self):
        # Loads the rendered pdf page to a global image var
        pageImg = self.pdfdoc.page(self.pdf_page_idex)
        unitPDF = self.getPdfUserUnits(self.pdf_page_idex)
        if self.bResetOffsetRotation:
            self.projectorWidget.resetOffsetRotation()
        self.projectorWidget.setPdfImage(pageImg.renderToImage(self.projectorDPI * unitPDF, self.projectorDPI * unitPDF))
        self.setCursor(Qt.ArrowCursor)
        self.projectorWidget.setCursor(Qt.OpenHandCursor)

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

class ProjectorPaintWidget(QWidget):
    def __init__(self, projectoWidth, projectorHeight, projectorScreen, fullscreenmode, projectorDPI):
        self.dragModeIsRotation = False
        self.prev_xevent = 0
        self.prev_yevent = 0
        self.rotation = 0.0
        self.scale = 0.5
        self.bMirror = False
        self.bInvertColorsProjector = False
        self.bInvertColorsPreviewer = False
        self.bSlowMode = False
        self.xoffset = 0
        self.yoffset = 0
        self.arrowKeyDelta = 0.5 * float(projectorDPI) / 2.54
        self.projectorWidth = projectoWidth
        self.projectorHeight = projectorHeight
        super().__init__()
        self.timerDelayHSVRedraw = QTimer()
        self.timerDelayHSVRedraw.setSingleShot(False)
        self.timerDelayHSVRedraw.timeout.connect(self.timer_delay_hsvredraw)
        self.timerDelayHSVRedraw.start(1)
        self.bRedrawHSVImage = False
        self.threadHSVRecompute = threading.Thread(target=self.thread_hsvRecompute)
        self.mutexHSV = threading.Lock()
        self.bForceRedrawByTimmer = False
        initImg = QPixmap(self.projectorWidth, self.projectorHeight)
        initImg.fill(Qt.gray)
        self.img = initImg.toImage()  # This is the displayed image
        self.imgHSVOverlay = None #This is the part of the image used as hsv overlay
        self.pdfHSVimg = None  # This is the pdf rendered to an opencv HSV image
        self.Hue_offset_current = 0  # Hue rotation angle from 0 to 179
        self.Hue_offset_target = 0  # Hue rotation angle from 0 to 179
        self.Sat_mult_current = 1  # Saturation multiplier
        self.Sat_mult_target = 1  # Saturation multiplier
        self.Val_mult_current = 1  # Value multiplier
        self.Val_mult_target = 1  # Value multiplier
        self.Line_Thickness = 0 #Erode value

        self.setCursor(Qt.OpenHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self.resize(self.img.width(), self.img.height())

        self.projectorWindow = prjWin.ProjectorWindow(projectorScreen, self.projectorWidth,
                                               self.projectorHeight, fullscreenmode, projectorDPI)

        self.projectorWindow.setWindowTitle("Projector Window")
        self.projectorWindow.show()

    def resetOffsetRotation(self):
        self.setScale(min(self.projectorWidth / self.img.width(),
                                          self.projectorHeight / self.img.height()))
        self.setOffsetRotation(int(self.img.width() / 2), int(self.img.height() / 2), 0)

    def setPdfImage(self, pdf_image):
        self.mutexHSV.acquire()
        self.img = pdf_image
        self.mutexHSV.release()

        rawImg = self.img.convertToFormat(QImage.Format_ARGB32)
        ptr = rawImg.constBits()
        ptr.setsize(rawImg.height() * rawImg.width() * rawImg.depth() // 8)
        self.pdfHSVimg = np.ndarray(shape=(rawImg.height(), rawImg.width(), rawImg.depth() // 8), buffer=ptr,
                                    dtype=np.uint8)
        self.pdfHSVimg = self.pdfHSVimg[:, :, 0:3]  # Discard alpha channel, the image is reversed so the actual format is BGRA
        self.pdfHSVimg = cv.cvtColor(self.pdfHSVimg, cv.COLOR_BGR2HSV)

        #Change saturation of the original imatge
        arr = self.pdfHSVimg.copy()
        arr[:, :, 1] = cv.multiply(arr[:, :, 1], 0.2)
        arr = cv.cvtColor(arr, cv.COLOR_HSV2BGR)

        alphaChannel = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=np.uint8)
        arr = np.concatenate((arr, alphaChannel), axis=2)
        self.img = QImage(arr.tobytes(), arr.shape[1], arr.shape[0], QImage.Format_ARGB32)

        self.bForceRedrawByTimmer = True  # Force redraw in the next cycle

    def setMirror(self, bMirror):
        self.bMirror = bMirror
        self.bForceRedrawByTimmer = True

    def setInvertColors(self, bInvertProjector, bInvertPreview):
        self.bInvertColorsProjector = bInvertProjector
        self.bInvertColorsPreviewer = bInvertPreview
        self.bForceRedrawByTimmer = True

    def setOffsetRotation(self, xoff, yoff, angle):
        self.xoffset = xoff
        self.yoffset = yoff
        self.rotation = angle
        self.bForceRedrawByTimmer = True

    def setHSVColorEffects(self, hue_offset, sat_multiplier, val_multipler ):
        self.Hue_offset_target = hue_offset
        self.Sat_mult_target = sat_multiplier
        self.Val_mult_target = val_multipler
        # The redraw is handled byt the hsv redraw timmer, nothing to do here

    def setThickness(self, thickness_value):
        self.Line_Thickness = thickness_value
        self.repaint()

    def setScale(self, scale):
        max_scale_w = self.width() / self.projectorWidth
        max_scale_h = self.height() / self.projectorHeight
        max_scale = min(max_scale_w, max_scale_h)
        if scale > max_scale:
            scale = max_scale
        self.scale = scale
        self.bForceRedrawByTimmer = True

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
                self.setOffsetRotation(self.xoffset, self.yoffset, self.rotation-ydiff*0.2)
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
                self.setOffsetRotation(self.xoffset, self.yoffset, angle)
        else:
            self.prev_xevent = event.x()
            self.prev_yevent = event.y()
            if self.bSlowMode:
                xdiff = 0.1 * xdiff
                ydiff = 0.1 * ydiff
            xdiffrotated = xdiff * math.cos(self.rotation * math.pi / 180) + ydiff * math.sin(self.rotation * math.pi / 180)
            ydiffrotated = -xdiff * math.sin(self.rotation * math.pi / 180) + ydiff * math.cos(self.rotation * math.pi / 180)
            self.setOffsetRotation(int((self.xoffset - xdiffrotated / self.scale)), int((self.yoffset - ydiffrotated / self.scale)), self.rotation)
    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.setScale(self.scale * 1.2)
        elif event.angleDelta().y() < 0:
            self.setScale(self.scale * 0.8)
        #print(f"Wheel delta: ({event.angleDelta().y()})")
    def offsetImageArrowKeys(self, xdelta, ydelta):
        xdiffrotated = xdelta * math.cos(self.rotation * math.pi / 180) + ydelta * math.sin(self.rotation * math.pi / 180)
        ydiffrotated = -xdelta * math.sin(self.rotation * math.pi / 180) + ydelta * math.cos(self.rotation * math.pi / 180)
        self.setOffsetRotation(int((self.xoffset - xdiffrotated / self.scale)),
                               int((self.yoffset - ydiffrotated / self.scale)), self.rotation)
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = True
            self.setCursor(Qt.PointingHandCursor)
        if e.key() == Qt.Key_Up:
            self.offsetImageArrowKeys(0, -self.arrowKeyDelta)
        if e.key() == Qt.Key_Down:
            self.offsetImageArrowKeys(0, self.arrowKeyDelta)
        if e.key() == Qt.Key_Left:
            self.offsetImageArrowKeys(-self.arrowKeyDelta, 0)
        if e.key() == Qt.Key_Right:
            self.offsetImageArrowKeys(self.arrowKeyDelta, 0)
    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Alt:
            self.bSlowMode = False
            self.setCursor(Qt.OpenHandCursor)
    def focusOutEvent(self, e):
        self.bSlowMode = False
        self.setCursor(Qt.OpenHandCursor)
    def closeEvent(self, event):
        if self.threadHSVRecompute.is_alive():
            self.threadHSVRecompute.join()
        self.projectorWindow.setCloseFlag()
        self.projectorWindow.close()
        event.accept()

    def timer_delay_hsvredraw(self):
        if not self.threadHSVRecompute.is_alive():
            if self.bRedrawHSVImage:
                self.bForceRedrawByTimmer = False
                self.bRedrawHSVImage = False
                self.threadHSVRecompute.join()
                self.repaint()
            if (((self.Hue_offset_current != self.Hue_offset_target) or
                    (self.Sat_mult_current != self.Sat_mult_target) or
                    (self.Val_mult_current != self.Val_mult_target)) or
                    self.bForceRedrawByTimmer):
                self.threadHSVRecompute = threading.Thread(target=self.thread_hsvRecompute)
                self.threadHSVRecompute.start()

    def thread_hsvRecompute(self):
        self.bRedrawHSVImage = True
        if self.pdfHSVimg is not None:
            hueoffset = self.Hue_offset_target
            satmult = self.Sat_mult_target
            valmult = self.Val_mult_target

            #Pre-mirror
            if self.bMirror:
                arr = cv.flip(self.pdfHSVimg, 1)
            else:
                arr = self.pdfHSVimg

            # Offset and rotation on the projector overlay
            rotMat = cv.getRotationMatrix2D((self.xoffset, self.yoffset), -self.rotation, 1.0)
            rotMat[0][2] += (self.projectorWidth / 2) - self.xoffset
            rotMat[1][2] += (self.projectorHeight / 2) - self.yoffset
            arr = cv.warpAffine(arr, rotMat, (self.projectorWidth, self.projectorHeight),
                                           borderMode=cv.BORDER_CONSTANT, borderValue=(0, 0, 255)) #Caution! the Border color is in HSV!

            arr[:, :, 0] = arr[:, :, 0] + hueoffset #Using this method instead of cv.add to get built-in overflo0w for color rotation
            arr[:, :, 1] = cv.multiply(arr[:, :, 1], satmult)
            arr[:, :, 2] = cv.multiply(arr[:, :, 2], valmult)

            arr = cv.cvtColor(arr, cv.COLOR_HSV2BGR)
            alphaChannel = np.full((arr.shape[0], arr.shape[1], 1), 255, dtype=np.uint8)
            arr = np.concatenate((arr, alphaChannel), axis=2)

            self.mutexHSV.acquire()
            self.imgHSVOverlay = QImage(arr.tobytes(), arr.shape[1], arr.shape[0], QImage.Format_ARGB32)
            self.mutexHSV.release()

            self.Hue_offset_current = hueoffset
            self.Sat_mult_current = satmult
            self.Val_mult_current = valmult

    def paintEvent(self, event):
        qp = QPainter(self)

        viewArea = QRect(0, 0, self.width(), self.height())
        viewAreaCenter = viewArea.center()
        winProjector = QRect(0, 0, int(self.projectorWidth*self.scale), int(self.projectorHeight*self.scale))

        qp.save()
        if self.bInvertColorsPreviewer:
            qp.fillRect(viewArea, Qt.black)
        else:
            qp.fillRect(viewArea, Qt.white)
        qp.restore()

        # Draw PDF render no HSV overlay
        qp.save()
        qp.translate(viewAreaCenter)
        qp.rotate(self.rotation)
        qp.scale(self.scale, self.scale)
        drawImg = self.img.mirrored(self.bMirror, False)
        if self.bInvertColorsPreviewer:
            drawImg.invertPixels()
        qp.drawPixmap(-self.xoffset,-self.yoffset, QPixmap.fromImage(drawImg))
        qp.restore()

        #Draw PDF render HSV overlay
        if self.imgHSVOverlay is not None:
            qp.save()
            qp.translate(viewAreaCenter)
            qp.scale(self.scale, self.scale)
            self.mutexHSV.acquire()
            drawImg = self.imgHSVOverlay.copy()
            self.mutexHSV.release()

            # Redraw the projector window
            self.projectorWindow.redraw(drawImg, self.bInvertColorsProjector, self.Line_Thickness)

            if self.bInvertColorsPreviewer:
                drawImg.invertPixels()
            qp.drawPixmap(-drawImg.width()//2, -drawImg.height()//2, QPixmap.fromImage(drawImg))
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