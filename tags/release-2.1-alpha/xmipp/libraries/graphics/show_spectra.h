/***************************************************************************
 *
 * Authors:     Carlos Oscar S. Sorzano (coss@cnb.uam.es)
 *              Alberto Pascual (pascual@cnb.uam.es)
 *
 * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
 * 02111-1307  USA
 *
 *  All comments concerning this program package may be sent to the
 *  e-mail address 'xmipp@cnb.uam.es'
 ***************************************************************************/

#ifndef SHOWSPECTRA_H
#define SHOWSPECTRA_H

#include "show_selfile.h"

#include <classification/training_vector.h>

#include <qscrollbar.h>
#include <qlabel.h>

/**@defgroup ShowSpectra Show Spectra Data
   @ingroup GraphicsLibrary */
//@{
/** Class to show spectra.
*/
class ShowSpectra: public ShowSel
{
    Q_OBJECT;
protected:
    // Vectors to represent
    xmippCTVectors *V;

    // Axes offset within cell frame
    int offX, offY;
    // spacing between X ticks
    int spacing;
    // Offset for ticks
    int x_tick_off;

    // Background Color
    QColor backColor;
    // Curve Color
    QColor curveColor;
    // Axis color
    QColor axisColor;
    // Font for axes
    QFont axisFont;

    // Some menu items to enable/disable them
    int mi_showgrid,    mi_hidegrid,
    mi_showXlegend, mi_hideXlegend,
    mi_showYlegend, mi_hideYlegend;

    /* Initialization.
       Sets V = NULL; and then calls to ShowSel::init() */
    virtual void init();
    /* Clear everything */
    virtual void clear();
    /* Initialize right click menubar */
    virtual void initRightclickMenubar();
    /* How to repaint the cell.
       This is the main function. */
    virtual void paintCell(QPainter *p, int row, int col, const QRect & cr,
                           bool selected, const QColorGroup & cg);
    /* Produce Pixmap for cell i */
    virtual void producePixmapAt(int i)
    {}
    /* Open a new file. Old parameters must be discarded */
    void openNewFile(const FileName &);
    /* Read a Dat File.
       First some initialization is done and then it call readDatFile*/
    virtual void readFile(const FileName &_fn,
                          double _minGray = 0, double _maxGray = 0);
    // Really read a Dat file
    virtual void readDatFile(const FileName &_fn_root);
    /* Init from vectors.
       Initialize many variables from the information contained in the
       vectors.*/
    virtual void initFromVectors();
    /* GUI Change Color */
    void GUIchangeColor(QColor &_color, const char * _color_title);
    /* set common spectra options*/
    void setCommonSpectraOptionsRightclickMenubar(void);
public:
    /* Apply filter */
    void applyFilter(const std::vector<int> &min, const std::vector<int> &max);
protected slots:
    // These slots are related with the right click menubar ---------------- */
    // Select spectra by value
    virtual void selectByValues();
    // Change Show/Hide Grid
    virtual void changeGrid();
    // Change Show/Hide X legend
    virtual void changeXlegend();
    // Change Show/Hide Y legend
    virtual void changeYlegend();
    // Show Avg and SD spectra
    virtual void showSpectraStats();
    // Change background color
    virtual void changeBackColor();
    // Change Curve color
    virtual void changeCurveColor();
    // Change Axis color
    virtual void changeAxisColor();
    // Change Font
    virtual void changeFont();
    // Change ticks spacing
    virtual void changeXstep();
    // returns spacing from scroll window
    virtual void set_spacing(std::vector<float> prm);

public:
    /** Initialize with a set of vectors.
        The same as with initWithFile but without reading any file.
    The memory pointed by _V should not be destroyed after calling
    this function since it will be the vectors seen by this class,
    i.e., no copy will be performed.*/
    virtual void initWithVectors(int _numRows, int _numCols,
                                 xmippCTVectors *_V, const char *_title);
};

/** Class to filter spectra.
*/
class SpectraFilter : public QWidget
{
    Q_OBJECT
public:
    /** Constructor */
    SpectraFilter(int min, int max, const std::vector<float> &_x,
                  ShowSpectra *show_spectra,
                  QWidget *parent = 0, const char *name = 0, int wflags = 0);
    /** Destructor */
    ~SpectraFilter();
private:
    ShowSpectra *__show_spectra;
    int         __N;    // Number of sliders
    float      *__current_values;
    QScrollBar **__scroll_min;
    QScrollBar **__scroll_max;
    QLabel     **__label_min;
    QLabel     **__label_max;
private slots:
    void but_ok_clicked();
    void scrollValueChanged(int);
};

//@}
#endif
