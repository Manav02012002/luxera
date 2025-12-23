"""
Luxera 3D Viewer with IES File Support

Load real luminaire photometry for accurate calculations.
Run with: python -m luxera.viewer.demo
"""

import sys
import math
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QSplitter, QStatusBar, QFrame, QFileDialog, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from OpenGL.GL import *
from OpenGL.GLU import *


def jet_colormap(value: float) -> Tuple[float, float, float]:
    """Convert 0-1 value to RGB using jet colormap."""
    value = max(0.0, min(1.0, value))
    
    if value < 0.25:
        r, g, b = 0, 4 * value, 1
    elif value < 0.5:
        r, g, b = 0, 1, 1 - 4 * (value - 0.25)
    elif value < 0.75:
        r, g, b = 4 * (value - 0.5), 1, 0
    else:
        r, g, b = 1, 1 - 4 * (value - 0.75), 0
    
    return (r, g, b)


class Camera:
    """Simple orbit camera."""
    
    def __init__(self):
        self.target = np.array([3.0, 4.0, 1.4])
        self.distance = 15.0
        self.azimuth = 45.0
        self.elevation = 30.0
    
    @property
    def position(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        x = self.distance * math.cos(el) * math.sin(az)
        y = self.distance * math.cos(el) * math.cos(az)
        z = self.distance * math.sin(el)
        return self.target + np.array([x, y, z])
    
    def orbit(self, dx, dy):
        self.azimuth += dx
        self.elevation = np.clip(self.elevation + dy, -89, 89)
    
    def pan(self, dx, dy):
        scale = self.distance * 0.002
        az = math.radians(self.azimuth)
        right = np.array([math.cos(az), -math.sin(az), 0])
        up = np.array([0, 0, 1])
        self.target += right * dx * scale + up * dy * scale
    
    def zoom(self, delta):
        self.distance = np.clip(self.distance * (1 - delta * 0.1), 1, 100)


class IESData:
    """Parsed IES photometric data for calculations."""
    
    def __init__(self):
        self.name = "Generic LED Panel"
        self.lumens = 5000
        self.watts = 50
        self.vertical_angles = np.array([0, 30, 60, 90])
        self.horizontal_angles = np.array([0, 90, 180, 270])
        self.candela = np.array([
            [2500, 2500, 2500, 2500],
            [2200, 2200, 2200, 2200],
            [1200, 1200, 1200, 1200],
            [0, 0, 0, 0],
        ])
    
    def get_intensity(self, vertical_deg: float, horizontal_deg: float = 0) -> float:
        """Interpolate candela value at given angles."""
        v = np.clip(vertical_deg, 0, 90)
        h = horizontal_deg % 360
        
        # Simple linear interpolation on vertical angle
        if len(self.vertical_angles) < 2:
            return float(self.candela[0, 0])
        
        # Find bracketing indices
        v_idx = np.searchsorted(self.vertical_angles, v)
        if v_idx == 0:
            return float(self.candela[0, 0])
        if v_idx >= len(self.vertical_angles):
            return float(self.candela[-1, 0])
        
        # Interpolate
        v0, v1 = self.vertical_angles[v_idx - 1], self.vertical_angles[v_idx]
        c0, c1 = self.candela[v_idx - 1, 0], self.candela[v_idx, 0]
        
        t = (v - v0) / (v1 - v0) if v1 != v0 else 0
        return float(c0 + t * (c1 - c0))


def parse_ies_file(filepath: str) -> Optional[IESData]:
    """Parse an IES file and return IESData object."""
    try:
        # Use luxera parser if available
        from luxera.parser.ies_parser import parse_ies_text
        
        content = Path(filepath).read_text()
        doc = parse_ies_text(content)
        
        ies = IESData()
        ies.name = doc.keywords.get('LUMINAIRE', ['Loaded IES'])[0]
        ies.lumens = doc.photometry.lamp_lumens
        ies.watts = doc.photometry.input_watts
        ies.vertical_angles = np.array(doc.angles.vertical)
        ies.horizontal_angles = np.array(doc.angles.horizontal)
        ies.candela = np.array(doc.candela.values)
        
        return ies
    except Exception as e:
        print(f"Error parsing IES: {e}")
        return None


class IlluminanceCalculator:
    """Illuminance calculator using IES data."""
    
    def __init__(self):
        self.ies_data: Optional[IESData] = None
        self.lumens_override: Optional[float] = None
    
    def set_ies(self, ies: IESData):
        self.ies_data = ies
        self.lumens_override = None
    
    def set_lumens(self, lumens: float):
        self.lumens_override = lumens
    
    def get_lumens(self) -> float:
        if self.lumens_override:
            return self.lumens_override
        if self.ies_data:
            return self.ies_data.lumens
        return 5000
    
    def calculate_grid(
        self,
        room_width: float,
        room_length: float,
        room_height: float,
        luminaires: List[Tuple[float, float, float]],
        grid_resolution: int = 25,
        work_plane_height: float = 0.8
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate illuminance on a grid."""
        x = np.linspace(0, room_width, grid_resolution)
        y = np.linspace(0, room_length, grid_resolution)
        X, Y = np.meshgrid(x, y)
        
        lux = np.zeros_like(X)
        lumens = self.get_lumens()
        
        for lum_x, lum_y, lum_z in luminaires:
            for i in range(grid_resolution):
                for j in range(grid_resolution):
                    px, py = X[i, j], Y[i, j]
                    pz = work_plane_height
                    
                    dx = px - lum_x
                    dy = py - lum_y
                    dz = pz - lum_z
                    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                    
                    if dist < 0.1:
                        continue
                    
                    # Angle from nadir (vertical down)
                    cos_theta = abs(dz) / dist
                    theta_deg = math.degrees(math.acos(cos_theta))
                    
                    # Get intensity from IES or use cosine distribution
                    if self.ies_data:
                        intensity = self.ies_data.get_intensity(theta_deg)
                        # Scale by lumens ratio if overridden
                        if self.lumens_override:
                            scale = self.lumens_override / max(self.ies_data.lumens, 1)
                            intensity *= scale
                    else:
                        # Simple cosine distribution
                        if theta_deg < 90:
                            intensity = lumens * cos_theta / (2 * math.pi)
                        else:
                            intensity = 0
                    
                    # Inverse square law with cosine incidence
                    E = intensity * cos_theta / (dist * dist)
                    lux[i, j] += E
        
        return X, Y, lux
    
    def get_statistics(self, lux: np.ndarray) -> dict:
        flat = lux.flatten()
        return {
            'min': float(np.min(flat)),
            'max': float(np.max(flat)),
            'avg': float(np.mean(flat)),
            'uniformity': float(np.min(flat) / np.mean(flat)) if np.mean(flat) > 0 else 0
        }


class LuxeraGLWidget(QOpenGLWidget):
    """OpenGL widget with false-color illuminance display."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = Camera()
        self._last_pos = None
        self._button = None
        
        self.room = (6.0, 8.0, 2.8)
        self.luminaires: List[Tuple[float, float, float]] = []
        
        self.lux_grid: Optional[np.ndarray] = None
        self.lux_X: Optional[np.ndarray] = None
        self.lux_Y: Optional[np.ndarray] = None
        self.lux_min = 0
        self.lux_max = 1000
        self.show_false_color = False
        
        self.calculator = IlluminanceCalculator()
        
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def initializeGL(self):
        glClearColor(0.15, 0.15, 0.18, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        glLightfv(GL_LIGHT0, GL_POSITION, [10, 10, 20, 1])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1])
        
        self._add_default_luminaires()
    
    def _add_default_luminaires(self):
        w, l, h = self.room
        for i in range(2):
            for j in range(3):
                x = w / 3 * (i + 1)
                y = l / 4 * (j + 1)
                self.luminaires.append((x, y, h))
    
    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, w / h if h else 1, 0.1, 1000)
    
    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        pos = self.camera.position
        target = self.camera.target
        gluLookAt(pos[0], pos[1], pos[2], target[0], target[1], target[2], 0, 0, 1)
        
        self._draw_grid()
        self._draw_room()
        self._draw_luminaires()
        
        if self.show_false_color and self.lux_grid is not None:
            self._draw_false_color_floor()
    
    def _draw_grid(self):
        glDisable(GL_LIGHTING)
        glColor3f(0.3, 0.3, 0.35)
        glBegin(GL_LINES)
        for i in range(-10, 11):
            glVertex3f(i, -10, 0)
            glVertex3f(i, 10, 0)
            glVertex3f(-10, i, 0)
            glVertex3f(10, i, 0)
        glEnd()
        glEnable(GL_LIGHTING)
    
    def _draw_room(self):
        w, l, h = self.room
        
        if not self.show_false_color or self.lux_grid is None:
            glColor3f(0.3, 0.3, 0.35)
            glBegin(GL_QUADS)
            glNormal3f(0, 0, 1)
            glVertex3f(0, 0, 0)
            glVertex3f(w, 0, 0)
            glVertex3f(w, l, 0)
            glVertex3f(0, l, 0)
            glEnd()
        
        glColor3f(0.9, 0.9, 0.85)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, -1)
        glVertex3f(0, 0, h)
        glVertex3f(0, l, h)
        glVertex3f(w, l, h)
        glVertex3f(w, 0, h)
        glEnd()
        
        glColor3f(0.8, 0.8, 0.75)
        for verts, norm in [
            ([(0,0,0), (0,l,0), (0,l,h), (0,0,h)], (1,0,0)),
            ([(w,0,0), (w,0,h), (w,l,h), (w,l,0)], (-1,0,0)),
            ([(0,0,0), (0,0,h), (w,0,h), (w,0,0)], (0,1,0)),
            ([(0,l,0), (w,l,0), (w,l,h), (0,l,h)], (0,-1,0)),
        ]:
            glBegin(GL_QUADS)
            glNormal3f(*norm)
            for v in verts:
                glVertex3f(*v)
            glEnd()
    
    def _draw_false_color_floor(self):
        glDisable(GL_LIGHTING)
        X, Y, lux = self.lux_X, self.lux_Y, self.lux_grid
        rows, cols = lux.shape
        lux_range = max(self.lux_max - self.lux_min, 1)
        
        glBegin(GL_QUADS)
        for i in range(rows - 1):
            for j in range(cols - 1):
                for di, dj in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                    x, y = X[i + di, j + dj], Y[i + di, j + dj]
                    val = (lux[i + di, j + dj] - self.lux_min) / lux_range
                    glColor3f(*jet_colormap(val))
                    glVertex3f(x, y, 0.01)
        glEnd()
        glEnable(GL_LIGHTING)
    
    def _draw_luminaires(self):
        glColor3f(1.0, 1.0, 0.8)
        size = 0.3
        for x, y, z in self.luminaires:
            glPushMatrix()
            glTranslatef(x, y, z - 0.02)
            glBegin(GL_QUADS)
            glNormal3f(0, 0, -1)
            glVertex3f(-size, -size, 0)
            glVertex3f(size, -size, 0)
            glVertex3f(size, size, 0)
            glVertex3f(-size, size, 0)
            glEnd()
            glPopMatrix()
    
    def calculate_illuminance(self) -> dict:
        w, l, h = self.room
        self.lux_X, self.lux_Y, self.lux_grid = self.calculator.calculate_grid(
            w, l, h, self.luminaires, grid_resolution=25
        )
        stats = self.calculator.get_statistics(self.lux_grid)
        self.lux_min = 0
        self.lux_max = max(stats['max'], 500)
        self.show_false_color = True
        self.update()
        return stats
    
    def clear_calculation(self):
        self.lux_grid = None
        self.show_false_color = False
        self.update()
    
    def set_ies(self, ies: IESData):
        self.calculator.set_ies(ies)
    
    def set_lumens(self, lumens: float):
        self.calculator.set_lumens(lumens)
    
    def mousePressEvent(self, e):
        self._last_pos = e.position()
        self._button = e.button()
    
    def mouseReleaseEvent(self, e):
        self._last_pos = None
        self._button = None
    
    def mouseMoveEvent(self, e):
        if not self._last_pos:
            return
        pos = e.position()
        dx, dy = pos.x() - self._last_pos.x(), pos.y() - self._last_pos.y()
        if self._button == Qt.LeftButton:
            self.camera.orbit(-dx * 0.5, dy * 0.5)
        elif self._button == Qt.MiddleButton:
            self.camera.pan(-dx, dy)
        self._last_pos = pos
        self.update()
    
    def wheelEvent(self, e):
        self.camera.zoom(e.angleDelta().y() / 120)
        self.update()
    
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F:
            self.fit_view()
        elif e.key() == Qt.Key_R:
            self.camera = Camera()
            self.update()
    
    def set_room(self, w, l, h):
        self.room = (w, l, h)
        self.camera.target = np.array([w/2, l/2, h/2])
        self.clear_calculation()
    
    def set_luminaires(self, gx, gy):
        self.luminaires.clear()
        w, l, h = self.room
        for i in range(gx):
            for j in range(gy):
                self.luminaires.append((w/(gx+1)*(i+1), l/(gy+1)*(j+1), h))
        self.clear_calculation()
    
    def fit_view(self):
        w, l, h = self.room
        self.camera.target = np.array([w/2, l/2, h/2])
        self.camera.distance = max(w, l, h) * 2
        self.camera.azimuth, self.camera.elevation = 45, 30
        self.update()


class ColorScaleWidget(QWidget):
    """Color scale legend."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_val, self.max_val = 0, 1000
        self.setFixedWidth(60)
        self.setMinimumHeight(200)
    
    def set_range(self, min_v, max_v):
        self.min_val, self.max_val = min_v, max_v
        self.update()
    
    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QFont
        p = QPainter(self)
        h = self.height()
        bar_top, bar_bottom = 20, h - 20
        bar_height = bar_bottom - bar_top
        
        for i in range(bar_height):
            r, g, b = jet_colormap(1.0 - i / bar_height)
            p.setPen(QColor(int(r*255), int(g*255), int(b*255)))
            p.drawLine(5, bar_top + i, 25, bar_top + i)
        
        p.setPen(QColor(100, 100, 100))
        p.drawRect(5, bar_top, 20, bar_height)
        
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont("", 9))
        p.drawText(28, bar_top + 10, f"{self.max_val:.0f}")
        p.drawText(28, bar_top + bar_height//2 + 5, f"{(self.max_val+self.min_val)/2:.0f}")
        p.drawText(28, bar_bottom, f"{self.min_val:.0f}")
        p.drawText(5, bar_top - 5, "lux")


class ViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luxera 3D Viewer")
        self.setMinimumSize(1100, 700)
        
        self.current_ies: Optional[IESData] = None
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        self.gl_widget = LuxeraGLWidget()
        
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        splitter.addWidget(self._create_controls())
        splitter.addWidget(self.gl_widget)
        
        self.color_scale = ColorScaleWidget()
        splitter.addWidget(self.color_scale)
        splitter.setSizes([240, 780, 60])
        
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Load an IES file or use generic luminaire")
    
    def _create_controls(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # IES File section
        ies_group = QGroupBox("Luminaire (IES)")
        ies_layout = QVBoxLayout(ies_group)
        
        self.ies_label = QLabel("Generic LED Panel\n5000 lm, 50 W")
        self.ies_label.setStyleSheet("font-size: 11px; color: #aaa;")
        ies_layout.addWidget(self.ies_label)
        
        load_btn = QPushButton("📁 Load IES File...")
        load_btn.clicked.connect(self._load_ies)
        ies_layout.addWidget(load_btn)
        
        layout.addWidget(ies_group)
        
        # Room
        room_group = QGroupBox("Room")
        room_layout = QVBoxLayout(room_group)
        
        self.room_width = QDoubleSpinBox()
        self.room_width.setRange(1, 50)
        self.room_width.setValue(6)
        self.room_width.setSuffix(" m")
        row = QHBoxLayout()
        row.addWidget(QLabel("Width:"))
        row.addWidget(self.room_width)
        room_layout.addLayout(row)
        
        self.room_length = QDoubleSpinBox()
        self.room_length.setRange(1, 50)
        self.room_length.setValue(8)
        self.room_length.setSuffix(" m")
        row = QHBoxLayout()
        row.addWidget(QLabel("Length:"))
        row.addWidget(self.room_length)
        room_layout.addLayout(row)
        
        self.room_height = QDoubleSpinBox()
        self.room_height.setRange(2, 10)
        self.room_height.setValue(2.8)
        self.room_height.setSuffix(" m")
        row = QHBoxLayout()
        row.addWidget(QLabel("Height:"))
        row.addWidget(self.room_height)
        room_layout.addLayout(row)
        
        layout.addWidget(room_group)
        
        # Luminaires
        lum_group = QGroupBox("Layout")
        lum_layout = QVBoxLayout(lum_group)
        
        self.lum_grid_x = QSpinBox()
        self.lum_grid_x.setRange(1, 10)
        self.lum_grid_x.setValue(2)
        row = QHBoxLayout()
        row.addWidget(QLabel("Grid X:"))
        row.addWidget(self.lum_grid_x)
        lum_layout.addLayout(row)
        
        self.lum_grid_y = QSpinBox()
        self.lum_grid_y.setRange(1, 10)
        self.lum_grid_y.setValue(3)
        row = QHBoxLayout()
        row.addWidget(QLabel("Grid Y:"))
        row.addWidget(self.lum_grid_y)
        lum_layout.addLayout(row)
        
        self.lum_lumens = QSpinBox()
        self.lum_lumens.setRange(500, 50000)
        self.lum_lumens.setValue(5000)
        self.lum_lumens.setSingleStep(500)
        self.lum_lumens.setSuffix(" lm")
        row = QHBoxLayout()
        row.addWidget(QLabel("Lumens:"))
        row.addWidget(self.lum_lumens)
        lum_layout.addLayout(row)
        
        layout.addWidget(lum_group)
        
        # Buttons
        apply_btn = QPushButton("Apply Layout")
        apply_btn.clicked.connect(self._apply)
        layout.addWidget(apply_btn)
        
        calc_btn = QPushButton("⚡ Calculate")
        calc_btn.setStyleSheet("font-weight: bold; padding: 8px; background: #2196F3; color: white;")
        calc_btn.clicked.connect(self._calculate)
        layout.addWidget(calc_btn)
        
        clear_btn = QPushButton("Clear Results")
        clear_btn.clicked.connect(self._clear)
        layout.addWidget(clear_btn)
        
        # Results
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        self.result_avg = QLabel("Average: -")
        self.result_min = QLabel("Min: -")
        self.result_max = QLabel("Max: -")
        self.result_uo = QLabel("Uniformity: -")
        self.result_compliance = QLabel("EN 12464-1: -")
        self.result_compliance.setStyleSheet("font-weight: bold;")
        
        for w in [self.result_avg, self.result_min, self.result_max, self.result_uo]:
            results_layout.addWidget(w)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        results_layout.addWidget(line)
        results_layout.addWidget(self.result_compliance)
        
        layout.addWidget(results_group)
        layout.addStretch()
        
        return panel
    
    def _load_ies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open IES File", "", "IES Files (*.ies);;All Files (*)"
        )
        if not path:
            return
        
        ies = parse_ies_file(path)
        if ies:
            self.current_ies = ies
            self.gl_widget.set_ies(ies)
            self.lum_lumens.setValue(int(ies.lumens))
            
            name = ies.name[:30] + "..." if len(ies.name) > 30 else ies.name
            self.ies_label.setText(f"{name}\n{ies.lumens:.0f} lm, {ies.watts:.0f} W")
            self.status.showMessage(f"Loaded: {Path(path).name}")
        else:
            self.status.showMessage("Failed to load IES file")
    
    def _apply(self):
        w = self.room_width.value()
        l = self.room_length.value()
        h = self.room_height.value()
        gx = self.lum_grid_x.value()
        gy = self.lum_grid_y.value()
        lumens = self.lum_lumens.value()
        
        self.gl_widget.set_room(w, l, h)
        self.gl_widget.set_luminaires(gx, gy)
        self.gl_widget.set_lumens(lumens)
        self.gl_widget.fit_view()
        
        self._clear_results()
        self.status.showMessage(f"Room: {w}×{l}×{h}m, {gx*gy} luminaires @ {lumens} lm")
    
    def _calculate(self):
        self._apply()
        stats = self.gl_widget.calculate_illuminance()
        
        self.result_avg.setText(f"Average: {stats['avg']:.0f} lux")
        self.result_min.setText(f"Min: {stats['min']:.0f} lux")
        self.result_max.setText(f"Max: {stats['max']:.0f} lux")
        self.result_uo.setText(f"Uniformity (Uo): {stats['uniformity']:.2f}")
        
        lux_ok = stats['avg'] >= 500
        uo_ok = stats['uniformity'] >= 0.6
        
        if lux_ok and uo_ok:
            self.result_compliance.setText("EN 12464-1: ✓ PASS")
            self.result_compliance.setStyleSheet("font-weight: bold; color: #4CAF50;")
        else:
            issues = []
            if not lux_ok:
                issues.append("need ≥500 lux")
            if not uo_ok:
                issues.append("need Uo ≥0.6")
            self.result_compliance.setText(f"EN 12464-1: ✗ FAIL\n({', '.join(issues)})")
            self.result_compliance.setStyleSheet("font-weight: bold; color: #f44336;")
        
        self.color_scale.set_range(0, stats['max'])
        self.status.showMessage(f"Avg: {stats['avg']:.0f} lux, Uo={stats['uniformity']:.2f}")
    
    def _clear(self):
        self.gl_widget.clear_calculation()
        self._clear_results()
    
    def _clear_results(self):
        for w in [self.result_avg, self.result_min, self.result_max, self.result_uo]:
            w.setText(w.text().split(":")[0] + ": -")
        self.result_compliance.setText("EN 12464-1: -")
        self.result_compliance.setStyleSheet("font-weight: bold;")


def main():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = ViewerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()