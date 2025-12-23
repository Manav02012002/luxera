"""
Luxera Qt OpenGL Widget

PySide6 widget for 3D scene rendering with mouse controls.
"""

import numpy as np
from typing import Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from luxera.viewer.renderer import Renderer, SceneObject
from luxera.viewer.mesh import (
    create_room_mesh, create_grid_mesh, 
    create_luminaire_mesh, Mesh
)


class LuxeraGLWidget(QOpenGLWidget):
    """
    OpenGL widget for 3D lighting scene visualization.
    
    Mouse controls:
    - Left drag: Orbit camera
    - Middle drag: Pan camera
    - Scroll: Zoom
    - Right click: Context menu (future)
    """
    
    # Signals
    object_selected = Signal(int)  # Emitted when object is clicked
    
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        
        self.renderer = Renderer()
        
        # Mouse state
        self._last_mouse_pos = None
        self._mouse_button = None
        
        # Enable mouse tracking
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Minimum size
        self.setMinimumSize(400, 300)
    
    def initializeGL(self):
        """Initialize OpenGL context."""
        self.renderer.initialize()
        
        # Add default grid
        grid = create_grid_mesh(20.0, 20, (0.3, 0.3, 0.35))
        self.renderer.add_object(SceneObject(grid, name="grid"))
    
    def resizeGL(self, width: int, height: int):
        """Handle widget resize."""
        self.renderer.resize(width, height)
    
    def paintGL(self):
        """Render the scene."""
        self.renderer.render(self.width(), self.height())
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse button press."""
        self._last_mouse_pos = event.position()
        self._mouse_button = event.button()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse button release."""
        self._last_mouse_pos = None
        self._mouse_button = None
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse movement."""
        if self._last_mouse_pos is None:
            return
        
        pos = event.position()
        dx = pos.x() - self._last_mouse_pos.x()
        dy = pos.y() - self._last_mouse_pos.y()
        
        if self._mouse_button == Qt.LeftButton:
            # Orbit
            self.renderer.camera.orbit(-dx * 0.5, dy * 0.5)
        elif self._mouse_button == Qt.MiddleButton:
            # Pan
            self.renderer.camera.pan(-dx, dy)
        
        self._last_mouse_pos = pos
        self.update()
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel (zoom)."""
        delta = event.angleDelta().y() / 120.0
        self.renderer.camera.zoom(delta)
        self.update()
    
    def keyPressEvent(self, event):
        """Handle key presses."""
        key = event.key()
        
        if key == Qt.Key_F:
            # Fit all
            self.renderer.fit_all()
            self.update()
        elif key == Qt.Key_R:
            # Reset camera
            self.renderer.camera = type(self.renderer.camera)()
            self.update()
        elif key == Qt.Key_G:
            # Toggle grid
            for obj in self.renderer.objects:
                if obj.name == "grid":
                    obj.visible = not obj.visible
            self.update()
    
    # Public API
    
    def add_room(
        self, 
        width: float, length: float, height: float,
        position: tuple = (0, 0, 0)
    ) -> int:
        """Add a room to the scene."""
        mesh = create_room_mesh(width, length, height)
        obj = SceneObject(
            mesh=mesh,
            position=np.array(position, dtype=np.float32),
            name="room"
        )
        idx = self.renderer.add_object(obj)
        self.update()
        return idx
    
    def add_luminaire(
        self,
        x: float, y: float, z: float,
        width: float = 0.6, length: float = 0.6
    ) -> int:
        """Add a luminaire to the scene."""
        mesh = create_luminaire_mesh(width, length)
        obj = SceneObject(
            mesh=mesh,
            position=np.array([x, y, z], dtype=np.float32),
            name="luminaire"
        )
        idx = self.renderer.add_object(obj)
        self.update()
        return idx
    
    def add_mesh(self, mesh: Mesh, position: tuple = (0, 0, 0), name: str = "") -> int:
        """Add a custom mesh to the scene."""
        obj = SceneObject(
            mesh=mesh,
            position=np.array(position, dtype=np.float32),
            name=name
        )
        idx = self.renderer.add_object(obj)
        self.update()
        return idx
    
    def clear_scene(self, keep_grid: bool = True):
        """Clear all objects from scene."""
        if keep_grid:
            grid_obj = None
            for obj in self.renderer.objects:
                if obj.name == "grid":
                    grid_obj = obj
                    break
            self.renderer.clear_objects()
            if grid_obj:
                self.renderer.add_object(grid_obj)
        else:
            self.renderer.clear_objects()
        self.update()
    
    def fit_view(self):
        """Fit camera to view all objects."""
        self.renderer.fit_all()
        self.update()
    
    def set_background_color(self, r: float, g: float, b: float):
        """Set background color (0-1 range)."""
        from OpenGL.GL import glClearColor
        self.renderer.background_color = (r, g, b, 1.0)
        self.makeCurrent()
        glClearColor(r, g, b, 1.0)
        self.update()


def create_demo_scene(widget: LuxeraGLWidget):
    """Create a demo lighting scene."""
    # Add room
    widget.add_room(6, 8, 2.8)
    
    # Add luminaires in a 2x3 grid
    spacing_x = 6 / 3
    spacing_y = 8 / 4
    
    for i in range(2):
        for j in range(3):
            x = spacing_x * (i + 1)
            y = spacing_y * (j + 1)
            z = 2.8  # Ceiling height
            widget.add_luminaire(x, y, z)
    
    widget.fit_view()
