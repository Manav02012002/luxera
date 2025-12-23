"""
Luxera OpenGL Renderer

Handles OpenGL state and drawing operations.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from luxera.viewer.camera import Camera
from luxera.viewer.mesh import Mesh, PrimitiveType
from luxera.viewer.shaders import (
    create_shader_program,
    VERTEX_SHADER, FRAGMENT_SHADER,
    FLAT_VERTEX_SHADER, FLAT_FRAGMENT_SHADER,
    GRID_VERTEX_SHADER, GRID_FRAGMENT_SHADER,
)


@dataclass
class SceneObject:
    """An object in the 3D scene."""
    mesh: Mesh
    position: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rotation: np.ndarray = field(default_factory=lambda: np.zeros(3))  # Euler degrees
    scale: np.ndarray = field(default_factory=lambda: np.ones(3))
    visible: bool = True
    name: str = ""
    
    def get_model_matrix(self) -> np.ndarray:
        """Get 4x4 model transformation matrix."""
        # Translation
        T = np.eye(4, dtype=np.float32)
        T[:3, 3] = self.position
        
        # Scale
        S = np.eye(4, dtype=np.float32)
        S[0, 0] = self.scale[0]
        S[1, 1] = self.scale[1]
        S[2, 2] = self.scale[2]
        
        # Rotation (simplified - just Z rotation for now)
        rz = np.radians(self.rotation[2])
        Rz = np.array([
            [np.cos(rz), -np.sin(rz), 0, 0],
            [np.sin(rz), np.cos(rz), 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float32)
        
        return T @ Rz @ S


class Renderer:
    """
    OpenGL renderer for Luxera 3D scenes.
    """
    
    def __init__(self):
        self.camera = Camera()
        self.objects: List[SceneObject] = []
        
        self.shader_lit = 0
        self.shader_flat = 0
        self.shader_grid = 0
        
        self.initialized = False
        self.background_color = (0.15, 0.15, 0.18, 1.0)
        
        # Lighting
        self.light_pos = np.array([10.0, 10.0, 20.0], dtype=np.float32)
        self.light_color = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        self.ambient = 0.3
    
    def initialize(self):
        """Initialize OpenGL state and shaders."""
        from OpenGL.GL import (
            glEnable, glClearColor, glClear,
            GL_DEPTH_TEST, GL_CULL_FACE, GL_BLEND,
            GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
            glBlendFunc, glLineWidth,
        )
        
        # Create shaders
        self.shader_lit = create_shader_program(VERTEX_SHADER, FRAGMENT_SHADER)
        self.shader_flat = create_shader_program(FLAT_VERTEX_SHADER, FLAT_FRAGMENT_SHADER)
        self.shader_grid = create_shader_program(GRID_VERTEX_SHADER, GRID_FRAGMENT_SHADER)
        
        # OpenGL state
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glLineWidth(1.0)
        
        glClearColor(*self.background_color)
        
        self.initialized = True
    
    def upload_mesh(self, mesh: Mesh):
        """Upload mesh data to GPU."""
        from OpenGL.GL import (
            glGenVertexArrays, glGenBuffers, glBindVertexArray,
            glBindBuffer, glBufferData, glVertexAttribPointer,
            glEnableVertexAttribArray,
            GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW, GL_FLOAT,
        )
        
        mesh.vao = glGenVertexArrays(1)
        glBindVertexArray(mesh.vao)
        
        # Vertices
        mesh.vbo_vertices = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_vertices)
        glBufferData(GL_ARRAY_BUFFER, mesh.vertices.nbytes, mesh.vertices, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
        glEnableVertexAttribArray(0)
        
        # Normals
        mesh.vbo_normals = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_normals)
        glBufferData(GL_ARRAY_BUFFER, mesh.normals.nbytes, mesh.normals, GL_STATIC_DRAW)
        glVertexAttribPointer(1, 3, GL_FLOAT, False, 0, None)
        glEnableVertexAttribArray(1)
        
        # Colors
        mesh.vbo_colors = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, mesh.vbo_colors)
        glBufferData(GL_ARRAY_BUFFER, mesh.colors.nbytes, mesh.colors, GL_STATIC_DRAW)
        glVertexAttribPointer(2, 3, GL_FLOAT, False, 0, None)
        glEnableVertexAttribArray(2)
        
        # Indices
        mesh.ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, mesh.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, mesh.indices.nbytes, mesh.indices, GL_STATIC_DRAW)
        
        glBindVertexArray(0)
    
    def add_object(self, obj: SceneObject) -> int:
        """Add object to scene, returns index."""
        if obj.mesh.vao == 0:
            self.upload_mesh(obj.mesh)
        self.objects.append(obj)
        return len(self.objects) - 1
    
    def clear_objects(self):
        """Remove all objects from scene."""
        self.objects.clear()
    
    def render(self, width: int, height: int):
        """Render the scene."""
        from OpenGL.GL import (
            glClear, glViewport, glUseProgram,
            glUniformMatrix4fv, glUniform3fv, glUniform1f,
            glGetUniformLocation, glBindVertexArray, glDrawElements,
            GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
            GL_TRIANGLES, GL_LINES, GL_UNSIGNED_INT,
        )
        
        if not self.initialized:
            self.initialize()
        
        glViewport(0, 0, width, height)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # Update camera aspect
        self.camera.aspect = width / height if height > 0 else 1.0
        
        view = self.camera.get_view_matrix()
        proj = self.camera.get_projection_matrix()
        
        # Draw lit objects
        glUseProgram(self.shader_lit)
        
        glUniformMatrix4fv(glGetUniformLocation(self.shader_lit, "view"), 1, True, view)
        glUniformMatrix4fv(glGetUniformLocation(self.shader_lit, "projection"), 1, True, proj)
        glUniform3fv(glGetUniformLocation(self.shader_lit, "viewPos"), 1, self.camera.position)
        glUniform3fv(glGetUniformLocation(self.shader_lit, "lightPos"), 1, self.light_pos)
        glUniform3fv(glGetUniformLocation(self.shader_lit, "lightColor"), 1, self.light_color)
        glUniform1f(glGetUniformLocation(self.shader_lit, "ambient"), self.ambient)
        
        for obj in self.objects:
            if not obj.visible:
                continue
            
            mesh = obj.mesh
            
            if mesh.primitive_type == PrimitiveType.LINES:
                # Use flat shader for lines
                glUseProgram(self.shader_flat)
                mvp = proj @ view @ obj.get_model_matrix()
                glUniformMatrix4fv(glGetUniformLocation(self.shader_flat, "mvp"), 1, True, mvp)
                
                glBindVertexArray(mesh.vao)
                glDrawElements(GL_LINES, mesh.num_indices, GL_UNSIGNED_INT, None)
                
                glUseProgram(self.shader_lit)
            else:
                model = obj.get_model_matrix()
                glUniformMatrix4fv(glGetUniformLocation(self.shader_lit, "model"), 1, True, model)
                
                glBindVertexArray(mesh.vao)
                glDrawElements(GL_TRIANGLES, mesh.num_indices, GL_UNSIGNED_INT, None)
        
        glBindVertexArray(0)
    
    def resize(self, width: int, height: int):
        """Handle viewport resize."""
        self.camera.aspect = width / height if height > 0 else 1.0
    
    def fit_all(self):
        """Fit camera to view all objects."""
        if not self.objects:
            return
        
        all_min = np.array([np.inf, np.inf, np.inf])
        all_max = np.array([-np.inf, -np.inf, -np.inf])
        
        for obj in self.objects:
            mesh_min, mesh_max = obj.mesh.get_bounds()
            mesh_min = mesh_min + obj.position
            mesh_max = mesh_max + obj.position
            
            all_min = np.minimum(all_min, mesh_min)
            all_max = np.maximum(all_max, mesh_max)
        
        self.camera.fit_to_bounds(all_min, all_max)
