#!/usr/bin/env python

############################################################################
#
#   Copyright (C) 2015
#    Jean-Paul Schouwstra
#
#   This file is part of DXF2GCODE.
#
#   DXF2GCODE is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   DXF2GCODE is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with DXF2GCODE.  If not, see <http://www.gnu.org/licenses/>.
#
############################################################################

import sys
import os
import logging
from copy import copy

from PyQt5.QtCore import Qt, QLocale, QTranslator, QCoreApplication
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QMainWindow, QApplication, QFileDialog

from Core.EntityContent import EntityContent
from Core.LayerContent import LayerContent
from Core.Shape import Shape
import Global.Globals as g
from Global.config import MyConfig
from Global.logger import LoggerClass
from Core.Point import Point
from DxfImport.Import import ReadDXF
from Gui.TreeHandling import TreeHandler
from dxf2gcode_ui import Ui_MainWindow


logger = logging.getLogger()

# Get folder of the main instance and write into globals
g.folder = os.path.dirname(os.path.abspath(sys.argv[0])).replace("\\", "/")
if os.path.islink(sys.argv[0]):
    g.folder = os.path.dirname(os.readlink(sys.argv[0]))


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.ui = Ui_MainWindow()

        self.ui.setupUi(self)

        self.glWidget = self.ui.canvas

        self.TreeHandler = TreeHandler(self.ui)

        self.ui.actionOpen.triggered.connect(self.open)
        self.ui.actionClose.triggered.connect(self.close)

        self.filename = ""

        self.shapes = []
        self.entityRoot = None
        self.layerContents = []

        self.cont_dx = 0.0
        self.cont_dy = 0.0
        self.cont_rotate = 0.0
        self.cont_scale = 1.0

    def tr(self, string_to_translate):
        """
        Translate a string using the QCoreApplication translation framework
        @param: string_to_translate: a unicode string
        @return: the translated unicode string if it was possible to translate
        """
        return QCoreApplication.translate("Main", string_to_translate, None)

    def open(self):
        self.filename, _ = QFileDialog.getOpenFileName(self, 'Open File', '',
                                                       # "All supported files (*.dxf *.ps *.pdf);;"
                                                       "DXF files (*.dxf);;"
                                                       # "PS files (*.ps);;"
                                                       # "PDF files (*.pdf);;"
                                                       "All types (*.*)")

        if self.filename:
            logger.info(self.tr("File: %s selected" % self.filename))
            self.setWindowTitle("DXF2GCODE - [%s]" % self.filename)
            self.load(self.filename)

    def load(self, filename):
        """
        Loads the file given by filename.  Also calls the command to
        make the plot.
        @param filename: String containing filename which should be loaded
        """
        self.glWidget.setCursor(Qt.WaitCursor)

        logger.info(self.tr('Loading file: %s' % filename))

        values = ReadDXF(filename)

        # Output the information in the text window
        logger.info(self.tr('Loaded layers: %s' % len(values.layers)))
        logger.info(self.tr('Loaded blocks: %s' % len(values.blocks.Entities)))
        for i in range(len(values.blocks.Entities)):
            layers = values.blocks.Entities[i].get_used_layers()
            logger.info(self.tr('Block %i includes %i Geometries; reduced to %i Contours; used layers %s'
                        % (i, len(values.blocks.Entities[i].geo), len(values.blocks.Entities[i].cont), layers)))
        layers = values.entities.get_used_layers()
        insert_nr = values.entities.get_insert_nr()
        logger.info(self.tr('Loaded %i entity geometries; reduced to %i contours; used layers %s; number of inserts %i'
                    % (len(values.entities.geo), len(values.entities.cont), layers, insert_nr)))

        self.makeShapes(values, Point(self.cont_dx, self.cont_dy), Point(),
                        [self.cont_scale, self.cont_scale, self.cont_scale],
                        self.cont_rotate)

        for shape in self.shapes:
            self.glWidget.addShape(shape)

        self.glWidget.autoScale()

        self.glWidget.paintOrientation()

        self.glWidget.unsetCursor()

    def makeShapes(self, values, p0, pb, sca, rot):
        self.entityRoot = EntityContent(nr=0, name='Entities',
                                        parent=None, children=[],
                                        p0=p0, pb=pb, sca=sca, rot=rot)
        del (self.layerContents[:])
        del (self.shapes[:])

        self.makeEntityShapes(values, self.entityRoot)

        self.layerContents.sort(key=lambda x: x.nr)

    def makeEntityShapes(self, values, parent):
        """
        Instance is called prior to plotting the shapes. It creates
        all shape classes which are later plotted into the graphics.

        @param parent: The parent of a shape is always an Entities. It may be root
        or, if it is a Block, this is the Block.
        """

        if parent.name == "Entities":
            entities = values.entities
        else:
            ent_nr = values.Get_Block_Nr(parent.name)
            entities = values.blocks.Entities[ent_nr]

        # Assigning the geometries in the variables geos & contours in cont
        ent_geos = entities.geo

        # Loop for the number of contours
        for cont in entities.cont:
            # Query if it is in the contour of an insert or of a block
            if ent_geos[cont.order[0][0]].Typ == "Insert":
                ent_geo = ent_geos[cont.order[0][0]]

                # Assign the base point for the block
                new_ent_nr = values.Get_Block_Nr(ent_geo.BlockName)
                new_entities = values.blocks.Entities[new_ent_nr]
                pb = new_entities.basep

                # Scaling, etc. assign the block
                p0 = ent_geos[cont.order[0][0]].Point
                sca = ent_geos[cont.order[0][0]].Scale
                rot = ent_geos[cont.order[0][0]].rot

                # Creating the new Entitie Contents for the insert
                newEntityContent = EntityContent(nr=0,
                                                 name=ent_geo.BlockName,
                                                 parent=parent, children=[],
                                                 p0=p0,
                                                 pb=pb,
                                                 sca=sca,
                                                 rot=rot)

                parent.addchild(newEntityContent)

                self.makeEntitiesShapes(values, newEntityContent)

            else:
                # Loop for the number of geometries
                self.shapes.append(Shape(len(self.shapes),
                                              cont.closed,
                                              40,
                                              0.0,
                                              parent,[]))

                for ent_geo_nr in range(len(cont.order)):
                    ent_geo = ent_geos[cont.order[ent_geo_nr][0]]
                    if cont.order[ent_geo_nr][1]:
                        ent_geo.geo.reverse()
                        for geo in ent_geo.geo:
                            geo = copy(geo)
                            geo.reverse()
                            self.appendshapes(geo)
                        ent_geo.geo.reverse()
                    else:
                        for geo in ent_geo.geo:
                            self.appendshapes(copy(geo))

                # All shapes have to be CCW direction.
                self.shapes[-1].AnalyseAndOptimize()
                self.shapes[-1].setNearestStPoint(parent.pb)

                self.addtoLayerContents(values, self.shapes[-1], ent_geo.Layer_Nr)
                parent.append(self.shapes[-1])

    def appendshapes(self, geo):
        self.shapes[-1].geos.append(geo)

    def addtoLayerContents(self, values, shape, lay_nr):
        # Check if the layer already exists and add shape if it is.
        for LayCon in self.layerContents:
            if LayCon.nr == lay_nr:
                LayCon.shapes.append(shape)
                shape.parentLayer = LayCon
                return

        # If the Layer does not exist create a new one.
        LayerName = values.layers[lay_nr].name
        self.layerContents.append(LayerContent(lay_nr, LayerName, [shape]))
        shape.parentLayer = self.layerContents[-1]


if __name__ == '__main__':
    app = QApplication(sys.argv)

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    Log = LoggerClass(logger)

    g.config = MyConfig()
    Log.set_console_handler_loglevel()
    Log.add_file_logger()

    #Get local language and install if available.
    locale = QLocale.system().name()
    logger.debug("locale: %s" %locale)
    translator = QTranslator()
    if translator.load("dxf2gcode_" + locale, "./i18n"):
        app.installTranslator(translator)

    window = MainWindow()
    g.window = window
    Log.add_window_logger(window.ui.messageBox)
    window.show()

    sys.exit(app.exec_())
