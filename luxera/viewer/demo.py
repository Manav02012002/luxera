"""
Luxera 3D Viewer with LENI Energy Calculation

EN 15193 Lighting Energy Numeric Indicator.
Run with: python -m luxera.viewer.demo
"""

import sys
import math
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QSplitter, QStatusBar, QFrame, QFileDialog, QMessageBox,
    QCheckBox, QLineEdit, QComboBox, QTabWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QSurfaceFormat, QImage
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from OpenGL.GL import *
from OpenGL.GLU import *


def jet_colormap(value: float) -> Tuple[float, float, float]:
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


def compute_contour_lines(X, Y, Z, level):
    rows, cols = Z.shape
    segments = []
    
    for i in range(rows - 1):
        for j in range(cols - 1):
            z00, z10, z01, z11 = Z[i,j], Z[i+1,j], Z[i,j+1], Z[i+1,j+1]
            x0, x1 = X[i,j], X[i,j+1]
            y0, y1 = Y[i,j], Y[i+1,j]
            
            case = 0
            if z00 >= level: case |= 1
            if z10 >= level: case |= 2
            if z01 >= level: case |= 4
            if z11 >= level: case |= 8
            
            if case == 0 or case == 15:
                continue
            
            def interp_x(za, zb, xa, xb):
                if abs(zb - za) < 1e-10: return (xa + xb) / 2
                return xa + (level - za) / (zb - za) * (xb - xa)
            
            def interp_y(za, zb, ya, yb):
                if abs(zb - za) < 1e-10: return (ya + yb) / 2
                return ya + (level - za) / (zb - za) * (yb - ya)
            
            bottom = (interp_x(z00, z01, x0, x1), y0) if (case & 1) != (case & 4) >> 2 else None
            top = (interp_x(z10, z11, x0, x1), y1) if (case & 2) >> 1 != (case & 8) >> 3 else None
            left = (x0, interp_y(z00, z10, y0, y1)) if (case & 1) != (case & 2) >> 1 else None
            right = (x1, interp_y(z01, z11, y0, y1)) if (case & 4) >> 2 != (case & 8) >> 3 else None
            
            edges = [e for e in [bottom, top, left, right] if e]
            if len(edges) == 2:
                segments.append((edges[0], edges[1]))
            elif len(edges) == 4:
                avg = (z00 + z10 + z01 + z11) / 4
                if avg >= level:
                    segments.append((bottom, left))
                    segments.append((top, right))
                else:
                    segments.append((bottom, right))
                    segments.append((top, left))
    return segments


# EN 15193 LENI Calculation
# ========================

# Building types with typical operating hours (tD, tN) and factors
BUILDING_TYPES = {
    "Office": {"tD": 2250, "tN": 250, "FD": 0.75, "FO": 0.80, "target_leni": 25},
    "Education (Classroom)": {"tD": 1800, "tN": 200, "FD": 0.80, "FO": 0.90, "target_leni": 20},
    "Healthcare": {"tD": 3000, "tN": 2000, "FD": 0.90, "FO": 0.95, "target_leni": 35},
    "Retail": {"tD": 3000, "tN": 500, "FD": 0.85, "FO": 0.95, "target_leni": 45},
    "Hotel (Rooms)": {"tD": 2000, "tN": 1000, "FD": 0.70, "FO": 0.60, "target_leni": 20},
    "Restaurant": {"tD": 1500, "tN": 1500, "FD": 0.75, "FO": 0.85, "target_leni": 30},
    "Industrial": {"tD": 2500, "tN": 500, "FD": 0.90, "FO": 0.95, "target_leni": 30},
    "Warehouse": {"tD": 2000, "tN": 500, "FD": 0.95, "FO": 0.70, "target_leni": 15},
    "Custom": {"tD": 2500, "tN": 250, "FD": 1.0, "FO": 1.0, "target_leni": 25},
}

# Daylight availability factors by facade type
DAYLIGHT_FACTORS = {
    "No windows": 1.0,
    "Small windows": 0.9,
    "Medium windows": 0.75,
    "Large windows/skylights": 0.6,
    "Fully glazed": 0.5,
}

# Occupancy control factors
OCCUPANCY_FACTORS = {
    "Manual switching only": 1.0,
    "Manual + time schedule": 0.95,
    "Presence detection (auto-on)": 0.90,
    "Presence detection (manual-on)": 0.80,
    "Presence + daylight dimming": 0.70,
}


def calculate_leni(
    total_watts: float,
    floor_area: float,
    building_type: str,
    daylight_type: str = "No windows",
    occupancy_type: str = "Manual switching only",
    custom_params: dict = None
) -> dict:
    """
    Calculate LENI according to EN 15193.
    
    LENI = (Pn × Fc × teff) / (A × 1000)
    
    Where:
    - Pn = total installed power (W)
    - Fc = constant illuminance factor (typically 1.0)
    - teff = effective operating time = (tD × FD × FO) + (tN × FO)
    - A = floor area (m²)
    
    Returns dict with LENI and all intermediate values.
    """
    if custom_params:
        params = custom_params
    else:
        params = BUILDING_TYPES.get(building_type, BUILDING_TYPES["Office"])
    
    tD = params["tD"]  # Daylight hours
    tN = params["tN"]  # Non-daylight hours
    FD_base = params["FD"]  # Base daylight factor
    FO_base = params["FO"]  # Base occupancy factor
    target = params["target_leni"]
    
    # Apply daylight availability
    FD = FD_base * DAYLIGHT_FACTORS.get(daylight_type, 1.0)
    
    # Apply occupancy control
    FO = FO_base * OCCUPANCY_FACTORS.get(occupancy_type, 1.0)
    
    # Constant illuminance factor (maintenance factor compensation)
    Fc = 1.0
    
    # Effective operating time (hours/year)
    t_eff = (tD * FD * FO) + (tN * FO)
    
    # Power density (W/m²)
    power_density = total_watts / floor_area if floor_area > 0 else 0
    
    # LENI (kWh/m²/year)
    leni = (total_watts * Fc * t_eff) / (floor_area * 1000) if floor_area > 0 else 0
    
    # Energy consumption (kWh/year)
    annual_energy = (total_watts * t_eff) / 1000
    
    # Rating
    if leni <= target * 0.6:
        rating = "A (Excellent)"
        rating_color = "#4CAF50"
    elif leni <= target * 0.8:
        rating = "B (Good)"
        rating_color = "#8BC34A"
    elif leni <= target:
        rating = "C (Standard)"
        rating_color = "#FFC107"
    elif leni <= target * 1.25:
        rating = "D (Below Average)"
        rating_color = "#FF9800"
    else:
        rating = "E (Poor)"
        rating_color = "#f44336"
    
    return {
        "leni": leni,
        "annual_energy": annual_energy,
        "power_density": power_density,
        "t_eff": t_eff,
        "tD": tD,
        "tN": tN,
        "FD": FD,
        "FO": FO,
        "target": target,
        "rating": rating,
        "rating_color": rating_color,
    }


class Camera:
    def __init__(self):
        self.target = np.array([3.0, 4.0, 1.4])
        self.distance = 15.0
        self.azimuth = 45.0
        self.elevation = 30.0
    
    @property
    def position(self):
        az, el = math.radians(self.azimuth), math.radians(self.elevation)
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
        self.target += right * dx * scale + np.array([0, 0, 1]) * dy * scale
    
    def zoom(self, delta):
        self.distance = np.clip(self.distance * (1 - delta * 0.1), 1, 100)


class IESData:
    def __init__(self):
        self.name = "Generic LED Panel"
        self.lumens = 5000
        self.watts = 50
        self.vertical_angles = np.array([0, 30, 60, 90])
        self.candela = np.array([[2500]*4, [2200]*4, [1200]*4, [0]*4])
    
    def get_intensity(self, vertical_deg):
        v = np.clip(vertical_deg, 0, 90)
        if len(self.vertical_angles) < 2:
            return float(self.candela[0, 0])
        v_idx = np.searchsorted(self.vertical_angles, v)
        if v_idx == 0:
            return float(self.candela[0, 0])
        if v_idx >= len(self.vertical_angles):
            return float(self.candela[-1, 0])
        v0, v1 = self.vertical_angles[v_idx - 1], self.vertical_angles[v_idx]
        c0, c1 = self.candela[v_idx - 1, 0], self.candela[v_idx, 0]
        t = (v - v0) / (v1 - v0) if v1 != v0 else 0
        return float(c0 + t * (c1 - c0))


def parse_ies_file(filepath):
    try:
        from luxera.parser.ies_parser import parse_ies_text
        content = Path(filepath).read_text()
        doc = parse_ies_text(content)
        ies = IESData()
        ies.name = doc.keywords.get('LUMINAIRE', ['Loaded IES'])[0]
        ies.lumens = doc.photometry.lamp_lumens
        ies.watts = doc.photometry.input_watts
        ies.vertical_angles = np.array(doc.angles.vertical)
        ies.candela = np.array(doc.candela.values)
        return ies
    except:
        return None


class IlluminanceCalculator:
    def __init__(self):
        self.ies_data = None
        self.lumens_override = None
    
    def set_ies(self, ies): self.ies_data = ies; self.lumens_override = None
    def set_lumens(self, lumens): self.lumens_override = lumens
    def get_lumens(self):
        if self.lumens_override: return self.lumens_override
        if self.ies_data: return self.ies_data.lumens
        return 5000
    
    def calculate_grid(self, room_width, room_length, room_height, luminaires, grid_resolution=25, work_plane_height=0.8):
        x = np.linspace(0, room_width, grid_resolution)
        y = np.linspace(0, room_length, grid_resolution)
        X, Y = np.meshgrid(x, y)
        lux = np.zeros_like(X)
        lumens = self.get_lumens()
        
        for lum_x, lum_y, lum_z in luminaires:
            for i in range(grid_resolution):
                for j in range(grid_resolution):
                    px, py, pz = X[i,j], Y[i,j], work_plane_height
                    dx, dy, dz = px - lum_x, py - lum_y, pz - lum_z
                    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                    if dist < 0.1: continue
                    cos_theta = abs(dz) / dist
                    theta_deg = math.degrees(math.acos(cos_theta))
                    
                    if self.ies_data:
                        intensity = self.ies_data.get_intensity(theta_deg)
                        if self.lumens_override:
                            intensity *= self.lumens_override / max(self.ies_data.lumens, 1)
                    else:
                        intensity = lumens * cos_theta / (2 * math.pi) if theta_deg < 90 else 0
                    
                    lux[i,j] += intensity * cos_theta / (dist * dist)
        return X, Y, lux
    
    def get_statistics(self, lux):
        flat = lux.flatten()
        return {
            'min': float(np.min(flat)), 'max': float(np.max(flat)),
            'avg': float(np.mean(flat)),
            'uniformity': float(np.min(flat) / np.mean(flat)) if np.mean(flat) > 0 else 0
        }


class LuxeraGLWidget(QOpenGLWidget):
    luminaire_count_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = Camera()
        self._last_pos = None
        self._button = None
        
        self.room = (6.0, 8.0, 2.8)
        self.luminaires = []
        self.hover_pos = None
        self.place_mode = False
        self.delete_mode = False
        
        self.lux_grid = None
        self.lux_X = None
        self.lux_Y = None
        self.lux_min = 0
        self.lux_max = 1000
        self.show_false_color = False
        self.show_contours = True
        self.contour_levels = [300, 400, 500, 600, 750]
        self.contour_segments = {}
        
        self.calculator = IlluminanceCalculator()
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
    
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
        if self.show_false_color and self.lux_grid is not None:
            self._draw_false_color_floor()
        if self.show_contours and self.contour_segments:
            self._draw_contours()
        self._draw_luminaires()
        if self.place_mode and self.hover_pos:
            self._draw_hover_luminaire()
    
    def _draw_grid(self):
        glDisable(GL_LIGHTING)
        glColor3f(0.3, 0.3, 0.35)
        glBegin(GL_LINES)
        for i in range(-10, 11):
            glVertex3f(i, -10, 0); glVertex3f(i, 10, 0)
            glVertex3f(-10, i, 0); glVertex3f(10, i, 0)
        glEnd()
        glEnable(GL_LIGHTING)
    
    def _draw_room(self):
        w, l, h = self.room
        if not self.show_false_color or self.lux_grid is None:
            glColor3f(0.3, 0.3, 0.35)
            glBegin(GL_QUADS)
            glNormal3f(0, 0, 1)
            glVertex3f(0, 0, 0); glVertex3f(w, 0, 0); glVertex3f(w, l, 0); glVertex3f(0, l, 0)
            glEnd()
        
        glColor3f(0.9, 0.9, 0.85)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, -1)
        glVertex3f(0, 0, h); glVertex3f(0, l, h); glVertex3f(w, l, h); glVertex3f(w, 0, h)
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
            for v in verts: glVertex3f(*v)
            glEnd()
    
    def _draw_false_color_floor(self):
        glDisable(GL_LIGHTING)
        X, Y, lux = self.lux_X, self.lux_Y, self.lux_grid
        rows, cols = lux.shape
        lux_range = max(self.lux_max - self.lux_min, 1)
        glBegin(GL_QUADS)
        for i in range(rows - 1):
            for j in range(cols - 1):
                for di, dj in [(0,0), (1,0), (1,1), (0,1)]:
                    x, y = X[i+di, j+dj], Y[i+di, j+dj]
                    val = (lux[i+di, j+dj] - self.lux_min) / lux_range
                    glColor3f(*jet_colormap(val))
                    glVertex3f(x, y, 0.01)
        glEnd()
        glEnable(GL_LIGHTING)
    
    def _draw_contours(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        for level, segments in self.contour_segments.items():
            r, g, b = jet_colormap(level / max(self.lux_max, 1))
            glColor3f(r * 0.8, g * 0.8, b * 0.8)
            glBegin(GL_LINES)
            for (x1, y1), (x2, y2) in segments:
                glVertex3f(x1, y1, 0.02); glVertex3f(x2, y2, 0.02)
            glEnd()
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)
    
    def _draw_luminaires(self):
        size = 0.3
        for idx, (x, y, z) in enumerate(self.luminaires):
            if self.delete_mode and self._is_near_luminaire(idx):
                glColor3f(1.0, 0.3, 0.3)
            else:
                glColor3f(1.0, 1.0, 0.8)
            glPushMatrix()
            glTranslatef(x, y, z - 0.02)
            glBegin(GL_QUADS)
            glNormal3f(0, 0, -1)
            glVertex3f(-size, -size, 0); glVertex3f(size, -size, 0)
            glVertex3f(size, size, 0); glVertex3f(-size, size, 0)
            glEnd()
            glPopMatrix()
    
    def _draw_hover_luminaire(self):
        x, y = self.hover_pos
        z, size = self.room[2], 0.3
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.2, 1.0, 0.2, 0.5)
        glPushMatrix()
        glTranslatef(x, y, z - 0.02)
        glBegin(GL_QUADS)
        glVertex3f(-size, -size, 0); glVertex3f(size, -size, 0)
        glVertex3f(size, size, 0); glVertex3f(-size, size, 0)
        glEnd()
        glPopMatrix()
        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)
    
    def _is_near_luminaire(self, idx):
        if not self.hover_pos or idx >= len(self.luminaires): return False
        hx, hy = self.hover_pos
        lx, ly, _ = self.luminaires[idx]
        return abs(hx - lx) < 0.5 and abs(hy - ly) < 0.5
    
    def _get_floor_position(self, screen_x, screen_y):
        self.makeCurrent()
        mv = glGetDoublev(GL_MODELVIEW_MATRIX)
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        try:
            near = gluUnProject(screen_x, vp[3] - screen_y, 0.0, mv, proj, vp)
            far = gluUnProject(screen_x, vp[3] - screen_y, 1.0, mv, proj, vp)
        except: return None
        ray_dir = np.array(far) - np.array(near)
        ray_origin = np.array(near)
        if abs(ray_dir[2]) < 1e-6: return None
        t = (self.room[2] - ray_origin[2]) / ray_dir[2]
        if t < 0: return None
        hit = ray_origin + t * ray_dir
        w, l = self.room[0], self.room[1]
        if 0 <= hit[0] <= w and 0 <= hit[1] <= l:
            return (hit[0], hit[1])
        return None
    
    def _find_luminaire_at(self, sx, sy):
        pos = self._get_floor_position(sx, sy)
        if not pos: return -1
        hx, hy = pos
        for idx, (lx, ly, _) in enumerate(self.luminaires):
            if abs(hx - lx) < 0.5 and abs(hy - ly) < 0.5:
                return idx
        return -1
    
    def _compute_contours(self):
        if self.lux_grid is None: return
        self.contour_segments.clear()
        for level in self.contour_levels:
            if level <= self.lux_max:
                segs = compute_contour_lines(self.lux_X, self.lux_Y, self.lux_grid, level)
                if segs: self.contour_segments[level] = segs
    
    def set_contour_levels(self, levels):
        self.contour_levels = sorted(levels)
        if self.lux_grid is not None:
            self._compute_contours()
            self.update()
    
    def grab_screenshot(self):
        self.makeCurrent()
        return self.grabFramebuffer()
    
    def save_screenshot(self, filepath):
        return self.grab_screenshot().save(filepath)
    
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.place_mode:
                pos = self._get_floor_position(int(e.position().x()), int(e.position().y()))
                if pos:
                    self.luminaires.append((pos[0], pos[1], self.room[2]))
                    self.luminaire_count_changed.emit(len(self.luminaires))
                    self.clear_calculation()
                return
            if self.delete_mode:
                idx = self._find_luminaire_at(int(e.position().x()), int(e.position().y()))
                if idx >= 0:
                    del self.luminaires[idx]
                    self.luminaire_count_changed.emit(len(self.luminaires))
                    self.clear_calculation()
                return
        self._last_pos = e.position()
        self._button = e.button()
    
    def mouseReleaseEvent(self, e):
        self._last_pos = None
        self._button = None
    
    def mouseMoveEvent(self, e):
        if self.place_mode or self.delete_mode:
            self.hover_pos = self._get_floor_position(int(e.position().x()), int(e.position().y()))
            self.update()
        if self._last_pos and not self.place_mode and not self.delete_mode:
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
        if e.key() == Qt.Key_F: self.fit_view()
        elif e.key() == Qt.Key_R: self.camera = Camera(); self.update()
        elif e.key() == Qt.Key_Escape:
            self.place_mode = False
            self.delete_mode = False
            self.hover_pos = None
            self.update()
    
    def set_place_mode(self, enabled):
        self.place_mode = enabled
        self.delete_mode = False
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        if not enabled: self.hover_pos = None
        self.update()
    
    def set_delete_mode(self, enabled):
        self.delete_mode = enabled
        self.place_mode = False
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        if not enabled: self.hover_pos = None
        self.update()
    
    def calculate_illuminance(self):
        w, l, h = self.room
        self.lux_X, self.lux_Y, self.lux_grid = self.calculator.calculate_grid(w, l, h, self.luminaires, 40)
        stats = self.calculator.get_statistics(self.lux_grid)
        self.lux_min = 0
        self.lux_max = max(stats['max'], 500)
        self.show_false_color = True
        self._compute_contours()
        self.update()
        return stats
    
    def clear_calculation(self):
        self.lux_grid = None
        self.show_false_color = False
        self.contour_segments.clear()
        self.update()
    
    def clear_luminaires(self):
        self.luminaires.clear()
        self.luminaire_count_changed.emit(0)
        self.clear_calculation()
    
    def add_grid_luminaires(self, gx, gy):
        self.luminaires.clear()
        w, l, h = self.room
        for i in range(gx):
            for j in range(gy):
                self.luminaires.append((w/(gx+1)*(i+1), l/(gy+1)*(j+1), h))
        self.luminaire_count_changed.emit(len(self.luminaires))
        self.clear_calculation()
    
    def set_ies(self, ies): self.calculator.set_ies(ies)
    def set_lumens(self, lumens): self.calculator.set_lumens(lumens)
    
    def set_room(self, w, l, h):
        self.room = (w, l, h)
        self.camera.target = np.array([w/2, l/2, h/2])
        self.clear_calculation()
    
    def fit_view(self):
        w, l, h = self.room
        self.camera.target = np.array([w/2, l/2, h/2])
        self.camera.distance = max(w, l, h) * 2
        self.camera.azimuth, self.camera.elevation = 45, 30
        self.update()


class ColorScaleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.min_val, self.max_val = 0, 1000
        self.contour_levels = []
        self.setFixedWidth(70)
        self.setMinimumHeight(200)
    
    def set_range(self, min_v, max_v):
        self.min_val, self.max_val = min_v, max_v
        self.update()
    
    def set_contour_levels(self, levels):
        self.contour_levels = levels
        self.update()
    
    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QColor, QFont, QPen
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
        
        if self.max_val > self.min_val:
            p.setPen(QPen(QColor(255, 255, 255), 2))
            for level in self.contour_levels:
                if self.min_val <= level <= self.max_val:
                    y_pos = bar_top + bar_height * (1 - (level - self.min_val) / (self.max_val - self.min_val))
                    p.drawLine(3, int(y_pos), 27, int(y_pos))
        
        p.setPen(QColor(200, 200, 200))
        p.setFont(QFont("", 9))
        p.drawText(30, bar_top + 10, f"{self.max_val:.0f}")
        p.drawText(30, bar_top + bar_height//2 + 5, f"{(self.max_val+self.min_val)/2:.0f}")
        p.drawText(30, bar_bottom, f"{self.min_val:.0f}")
        p.drawText(5, bar_top - 5, "lux")


def generate_pdf_report(filepath, room, luminaires, stats, ies_name, lumens, watts_per_lum, leni_result, screenshot_path=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    
    doc = SimpleDocTemplate(filepath, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, spaceAfter=20)
    story.append(Paragraph("Luxera Lighting Calculation Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Room info
    story.append(Paragraph("Room Information", styles['Heading2']))
    t = Table([
        ["Parameter", "Value"],
        ["Dimensions", f"{room[0]:.1f} × {room[1]:.1f} × {room[2]:.1f} m"],
        ["Floor Area", f"{room[0] * room[1]:.1f} m²"],
    ], colWidths=[80*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Luminaire info
    story.append(Paragraph("Luminaire Information", styles['Heading2']))
    total_watts = watts_per_lum * len(luminaires)
    t = Table([
        ["Parameter", "Value"],
        ["Luminaire", ies_name],
        ["Lumens/unit", f"{lumens:.0f} lm"],
        ["Watts/unit", f"{watts_per_lum:.0f} W"],
        ["Quantity", str(len(luminaires))],
        ["Total Power", f"{total_watts:.0f} W"],
        ["Power Density", f"{total_watts / (room[0]*room[1]):.1f} W/m²"],
    ], colWidths=[80*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Illuminance results
    story.append(Paragraph("Illuminance Results", styles['Heading2']))
    lux_ok = stats['avg'] >= 500
    uo_ok = stats['uniformity'] >= 0.6
    t = Table([
        ["Parameter", "Value", "Requirement", "Status"],
        ["Average", f"{stats['avg']:.0f} lux", "≥ 500 lux", "✓" if lux_ok else "✗"],
        ["Minimum", f"{stats['min']:.0f} lux", "-", "-"],
        ["Maximum", f"{stats['max']:.0f} lux", "-", "-"],
        ["Uniformity (Uo)", f"{stats['uniformity']:.2f}", "≥ 0.60", "✓" if uo_ok else "✗"],
    ], colWidths=[45*mm, 35*mm, 35*mm, 20*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
    ]))
    story.append(t)
    
    comp = "PASS" if (lux_ok and uo_ok) else "FAIL"
    comp_style = ParagraphStyle('Comp', parent=styles['Normal'], fontSize=12, 
                                textColor=colors.green if comp == "PASS" else colors.red)
    story.append(Spacer(1, 5))
    story.append(Paragraph(f"<b>EN 12464-1 Compliance: {comp}</b>", comp_style))
    story.append(Spacer(1, 15))
    
    # LENI results
    story.append(Paragraph("Energy Performance (EN 15193)", styles['Heading2']))
    t = Table([
        ["Parameter", "Value"],
        ["LENI", f"{leni_result['leni']:.1f} kWh/m²/year"],
        ["Target LENI", f"{leni_result['target']:.1f} kWh/m²/year"],
        ["Annual Energy", f"{leni_result['annual_energy']:.0f} kWh/year"],
        ["Effective Hours", f"{leni_result['t_eff']:.0f} h/year"],
        ["Rating", leni_result['rating']],
    ], colWidths=[80*mm, 60*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    # Screenshot
    if screenshot_path and Path(screenshot_path).exists():
        story.append(Paragraph("3D Visualization", styles['Heading2']))
        story.append(Image(screenshot_path, width=150*mm, height=110*mm))
    
    doc.build(story)


class ViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luxera 3D Viewer")
        self.setMinimumSize(1200, 750)
        
        self.current_ies = None
        self.last_stats = None
        self.last_leni = None
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        self.gl_widget = LuxeraGLWidget()
        self.gl_widget.luminaire_count_changed.connect(self._update_count)
        
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        splitter.addWidget(self._create_controls())
        splitter.addWidget(self.gl_widget)
        
        self.color_scale = ColorScaleWidget()
        self.color_scale.set_contour_levels(self.gl_widget.contour_levels)
        splitter.addWidget(self.color_scale)
        splitter.setSizes([300, 820, 70])
        
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")
    
    def _create_controls(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # === DESIGN TAB ===
        design_tab = QWidget()
        design_layout = QVBoxLayout(design_tab)
        
        # IES
        ies_group = QGroupBox("Luminaire")
        ies_layout = QVBoxLayout(ies_group)
        self.ies_label = QLabel("Generic LED Panel\n5000 lm, 50 W")
        self.ies_label.setStyleSheet("font-size: 11px; color: #aaa;")
        ies_layout.addWidget(self.ies_label)
        load_btn = QPushButton("📁 Load IES File...")
        load_btn.clicked.connect(self._load_ies)
        ies_layout.addWidget(load_btn)
        
        self.lum_lumens = QSpinBox()
        self.lum_lumens.setRange(500, 50000)
        self.lum_lumens.setValue(5000)
        self.lum_lumens.setSuffix(" lm")
        row = QHBoxLayout()
        row.addWidget(QLabel("Lumens:"))
        row.addWidget(self.lum_lumens)
        ies_layout.addLayout(row)
        
        self.lum_watts = QSpinBox()
        self.lum_watts.setRange(5, 500)
        self.lum_watts.setValue(50)
        self.lum_watts.setSuffix(" W")
        row = QHBoxLayout()
        row.addWidget(QLabel("Watts:"))
        row.addWidget(self.lum_watts)
        ies_layout.addLayout(row)
        
        design_layout.addWidget(ies_group)
        
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
        
        apply_room_btn = QPushButton("Apply Room")
        apply_room_btn.clicked.connect(self._apply_room)
        room_layout.addWidget(apply_room_btn)
        design_layout.addWidget(room_group)
        
        # Placement
        place_group = QGroupBox("Placement")
        place_layout = QVBoxLayout(place_group)
        
        self.lum_count_label = QLabel("Luminaires: 0")
        self.lum_count_label.setStyleSheet("font-weight: bold;")
        place_layout.addWidget(self.lum_count_label)
        
        self.place_btn = QPushButton("➕ Place Mode")
        self.place_btn.setCheckable(True)
        self.place_btn.clicked.connect(self._toggle_place_mode)
        place_layout.addWidget(self.place_btn)
        
        self.delete_btn = QPushButton("🗑️ Delete Mode")
        self.delete_btn.setCheckable(True)
        self.delete_btn.clicked.connect(self._toggle_delete_mode)
        place_layout.addWidget(self.delete_btn)
        
        grid_row = QHBoxLayout()
        self.grid_x = QSpinBox()
        self.grid_x.setRange(1, 10)
        self.grid_x.setValue(2)
        self.grid_y = QSpinBox()
        self.grid_y.setRange(1, 10)
        self.grid_y.setValue(3)
        grid_row.addWidget(QLabel("Grid:"))
        grid_row.addWidget(self.grid_x)
        grid_row.addWidget(QLabel("×"))
        grid_row.addWidget(self.grid_y)
        place_layout.addLayout(grid_row)
        
        add_grid_btn = QPushButton("Add Grid")
        add_grid_btn.clicked.connect(self._add_grid)
        place_layout.addWidget(add_grid_btn)
        
        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_luminaires)
        place_layout.addWidget(clear_btn)
        design_layout.addWidget(place_group)
        
        design_layout.addStretch()
        tabs.addTab(design_tab, "Design")
        
        # === ENERGY TAB ===
        energy_tab = QWidget()
        energy_layout = QVBoxLayout(energy_tab)
        
        energy_group = QGroupBox("EN 15193 LENI Settings")
        eg_layout = QVBoxLayout(energy_group)
        
        self.building_type = QComboBox()
        self.building_type.addItems(BUILDING_TYPES.keys())
        row = QHBoxLayout()
        row.addWidget(QLabel("Building Type:"))
        row.addWidget(self.building_type)
        eg_layout.addLayout(row)
        
        self.daylight_type = QComboBox()
        self.daylight_type.addItems(DAYLIGHT_FACTORS.keys())
        self.daylight_type.setCurrentIndex(2)  # Medium windows
        row = QHBoxLayout()
        row.addWidget(QLabel("Daylight:"))
        row.addWidget(self.daylight_type)
        eg_layout.addLayout(row)
        
        self.occupancy_type = QComboBox()
        self.occupancy_type.addItems(OCCUPANCY_FACTORS.keys())
        row = QHBoxLayout()
        row.addWidget(QLabel("Controls:"))
        row.addWidget(self.occupancy_type)
        eg_layout.addLayout(row)
        
        energy_layout.addWidget(energy_group)
        
        # LENI Results
        leni_group = QGroupBox("LENI Results")
        leni_layout = QVBoxLayout(leni_group)
        
        self.leni_value = QLabel("LENI: -")
        self.leni_value.setStyleSheet("font-size: 18px; font-weight: bold;")
        leni_layout.addWidget(self.leni_value)
        
        self.leni_target = QLabel("Target: -")
        leni_layout.addWidget(self.leni_target)
        
        self.leni_rating = QLabel("Rating: -")
        self.leni_rating.setStyleSheet("font-weight: bold;")
        leni_layout.addWidget(self.leni_rating)
        
        self.leni_annual = QLabel("Annual Energy: -")
        leni_layout.addWidget(self.leni_annual)
        
        self.leni_power = QLabel("Power Density: -")
        leni_layout.addWidget(self.leni_power)
        
        energy_layout.addWidget(leni_group)
        energy_layout.addStretch()
        tabs.addTab(energy_tab, "Energy")
        
        # === RESULTS TAB ===
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        
        results_group = QGroupBox("Illuminance Results")
        rg_layout = QVBoxLayout(results_group)
        
        self.result_avg = QLabel("Average: -")
        self.result_min = QLabel("Min: -")
        self.result_max = QLabel("Max: -")
        self.result_uo = QLabel("Uniformity: -")
        self.result_compliance = QLabel("EN 12464-1: -")
        self.result_compliance.setStyleSheet("font-weight: bold;")
        
        for w in [self.result_avg, self.result_min, self.result_max, self.result_uo]:
            rg_layout.addWidget(w)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        rg_layout.addWidget(line)
        rg_layout.addWidget(self.result_compliance)
        
        results_layout.addWidget(results_group)
        
        # Display options
        display_group = QGroupBox("Display")
        dg_layout = QVBoxLayout(display_group)
        
        self.show_contours_cb = QCheckBox("Show Iso-lux Contours")
        self.show_contours_cb.setChecked(True)
        self.show_contours_cb.toggled.connect(lambda c: setattr(self.gl_widget, 'show_contours', c) or self.gl_widget.update())
        dg_layout.addWidget(self.show_contours_cb)
        
        self.show_falsecolor_cb = QCheckBox("Show False Color")
        self.show_falsecolor_cb.setChecked(True)
        self.show_falsecolor_cb.toggled.connect(self._toggle_falsecolor)
        dg_layout.addWidget(self.show_falsecolor_cb)
        
        row = QHBoxLayout()
        row.addWidget(QLabel("Levels:"))
        self.contour_input = QLineEdit("300,400,500,600,750")
        self.contour_input.returnPressed.connect(self._update_contour_levels)
        row.addWidget(self.contour_input)
        dg_layout.addLayout(row)
        
        results_layout.addWidget(display_group)
        results_layout.addStretch()
        tabs.addTab(results_tab, "Results")
        
        # === BOTTOM BUTTONS ===
        calc_btn = QPushButton("⚡ Calculate")
        calc_btn.setStyleSheet("font-weight: bold; padding: 10px; background: #2196F3; color: white; font-size: 14px;")
        calc_btn.clicked.connect(self._calculate)
        layout.addWidget(calc_btn)
        
        export_row = QHBoxLayout()
        screenshot_btn = QPushButton("📷 Screenshot")
        screenshot_btn.clicked.connect(self._save_screenshot)
        export_row.addWidget(screenshot_btn)
        
        pdf_btn = QPushButton("📄 PDF Report")
        pdf_btn.clicked.connect(self._export_pdf)
        export_row.addWidget(pdf_btn)
        layout.addLayout(export_row)
        
        return panel
    
    def _update_count(self, count):
        self.lum_count_label.setText(f"Luminaires: {count}")
    
    def _toggle_place_mode(self):
        if self.place_btn.isChecked():
            self.delete_btn.setChecked(False)
            self.gl_widget.set_place_mode(True)
            self.status.showMessage("Click ceiling to place. ESC to exit.")
        else:
            self.gl_widget.set_place_mode(False)
    
    def _toggle_delete_mode(self):
        if self.delete_btn.isChecked():
            self.place_btn.setChecked(False)
            self.gl_widget.set_delete_mode(True)
            self.status.showMessage("Click luminaires to delete. ESC to exit.")
        else:
            self.gl_widget.set_delete_mode(False)
    
    def _toggle_falsecolor(self, checked):
        self.gl_widget.show_false_color = checked if self.gl_widget.lux_grid is not None else False
        self.gl_widget.update()
    
    def _update_contour_levels(self):
        try:
            levels = [float(x.strip()) for x in self.contour_input.text().split(",") if x.strip()]
            self.gl_widget.set_contour_levels(levels)
            self.color_scale.set_contour_levels(levels)
        except: pass
    
    def _apply_room(self):
        self.gl_widget.set_room(self.room_width.value(), self.room_length.value(), self.room_height.value())
        self.gl_widget.fit_view()
    
    def _add_grid(self):
        self.gl_widget.add_grid_luminaires(self.grid_x.value(), self.grid_y.value())
        self.gl_widget.fit_view()
    
    def _clear_luminaires(self):
        self.gl_widget.clear_luminaires()
        self.last_stats = None
        self.last_leni = None
    
    def _load_ies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open IES", "", "IES Files (*.ies)")
        if not path: return
        ies = parse_ies_file(path)
        if ies:
            self.current_ies = ies
            self.gl_widget.set_ies(ies)
            self.lum_lumens.setValue(int(ies.lumens))
            self.lum_watts.setValue(int(ies.watts))
            name = ies.name[:25] + "..." if len(ies.name) > 25 else ies.name
            self.ies_label.setText(f"{name}\n{ies.lumens:.0f} lm, {ies.watts:.0f} W")
    
    def _calculate(self):
        self.gl_widget.set_lumens(self.lum_lumens.value())
        
        if not self.gl_widget.luminaires:
            self.status.showMessage("No luminaires!")
            return
        
        self._update_contour_levels()
        stats = self.gl_widget.calculate_illuminance()
        self.last_stats = stats
        
        # Update illuminance results
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
            if not lux_ok: issues.append("≥500 lux")
            if not uo_ok: issues.append("Uo ≥0.6")
            self.result_compliance.setText(f"EN 12464-1: ✗ FAIL ({', '.join(issues)})")
            self.result_compliance.setStyleSheet("font-weight: bold; color: #f44336;")
        
        # Calculate LENI
        total_watts = self.lum_watts.value() * len(self.gl_widget.luminaires)
        floor_area = self.gl_widget.room[0] * self.gl_widget.room[1]
        
        leni = calculate_leni(
            total_watts, floor_area,
            self.building_type.currentText(),
            self.daylight_type.currentText(),
            self.occupancy_type.currentText()
        )
        self.last_leni = leni
        
        self.leni_value.setText(f"LENI: {leni['leni']:.1f} kWh/m²/year")
        self.leni_target.setText(f"Target: ≤ {leni['target']:.0f} kWh/m²/year")
        self.leni_rating.setText(f"Rating: {leni['rating']}")
        self.leni_rating.setStyleSheet(f"font-weight: bold; color: {leni['rating_color']};")
        self.leni_annual.setText(f"Annual Energy: {leni['annual_energy']:.0f} kWh/year")
        self.leni_power.setText(f"Power Density: {leni['power_density']:.1f} W/m²")
        
        self.color_scale.set_range(0, stats['max'])
        self.status.showMessage(f"Avg: {stats['avg']:.0f} lux | LENI: {leni['leni']:.1f} kWh/m²/yr ({leni['rating']})")
    
    def _save_screenshot(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "luxera.png", "PNG (*.png)")
        if path:
            self.gl_widget.save_screenshot(path)
            self.status.showMessage(f"Saved: {path}")
    
    def _export_pdf(self):
        if not self.last_stats or not self.last_leni:
            QMessageBox.warning(self, "No Results", "Calculate first!")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", "luxera_report.pdf", "PDF (*.pdf)")
        if not path: return
        
        import tempfile
        temp_dir = tempfile.mkdtemp()
        screenshot_path = Path(temp_dir) / "screenshot.png"
        self.gl_widget.save_screenshot(str(screenshot_path))
        
        try:
            ies_name = self.current_ies.name if self.current_ies else "Generic LED Panel"
            generate_pdf_report(
                path, self.gl_widget.room, self.gl_widget.luminaires,
                self.last_stats, ies_name, self.lum_lumens.value(),
                self.lum_watts.value(), self.last_leni, str(screenshot_path)
            )
            self.status.showMessage(f"PDF saved: {path}")
            QMessageBox.information(self, "Export Complete", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if screenshot_path.exists():
                screenshot_path.unlink()


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