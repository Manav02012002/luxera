"""
Luxera GLSL Shaders

Vertex and fragment shaders for 3D rendering.
"""

# Basic vertex shader with lighting
VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec3 color;

uniform mat4 model;
uniform mat4 view;
uniform mat4 projection;

out vec3 fragPos;
out vec3 fragNormal;
out vec3 fragColor;

void main() {
    vec4 worldPos = model * vec4(position, 1.0);
    fragPos = worldPos.xyz;
    fragNormal = mat3(transpose(inverse(model))) * normal;
    fragColor = color;
    gl_Position = projection * view * worldPos;
}
"""

# Phong lighting fragment shader
FRAGMENT_SHADER = """
#version 330 core

in vec3 fragPos;
in vec3 fragNormal;
in vec3 fragColor;

uniform vec3 viewPos;
uniform vec3 lightPos;
uniform vec3 lightColor;
uniform float ambient;

out vec4 outColor;

void main() {
    // Ambient
    vec3 ambientLight = ambient * lightColor;
    
    // Diffuse
    vec3 norm = normalize(fragNormal);
    vec3 lightDir = normalize(lightPos - fragPos);
    float diff = max(dot(norm, lightDir), 0.0);
    vec3 diffuse = diff * lightColor;
    
    // Specular
    vec3 viewDir = normalize(viewPos - fragPos);
    vec3 reflectDir = reflect(-lightDir, norm);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 32.0);
    vec3 specular = 0.3 * spec * lightColor;
    
    vec3 result = (ambientLight + diffuse + specular) * fragColor;
    outColor = vec4(result, 1.0);
}
"""

# Simple flat shader (no lighting)
FLAT_VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec3 position;
layout(location = 1) in vec3 color;

uniform mat4 mvp;

out vec3 fragColor;

void main() {
    fragColor = color;
    gl_Position = mvp * vec4(position, 1.0);
}
"""

FLAT_FRAGMENT_SHADER = """
#version 330 core

in vec3 fragColor;
out vec4 outColor;

void main() {
    outColor = vec4(fragColor, 1.0);
}
"""

# Grid shader
GRID_VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec3 position;

uniform mat4 mvp;

void main() {
    gl_Position = mvp * vec4(position, 1.0);
}
"""

GRID_FRAGMENT_SHADER = """
#version 330 core

uniform vec3 gridColor;
uniform float alpha;

out vec4 outColor;

void main() {
    outColor = vec4(gridColor, alpha);
}
"""

# False color shader for illuminance visualization
FALSE_COLOR_VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec3 position;
layout(location = 1) in float illuminance;

uniform mat4 mvp;
uniform float minLux;
uniform float maxLux;

out float luxValue;

void main() {
    luxValue = (illuminance - minLux) / (maxLux - minLux);
    gl_Position = mvp * vec4(position, 1.0);
}
"""

FALSE_COLOR_FRAGMENT_SHADER = """
#version 330 core

in float luxValue;
out vec4 outColor;

vec3 jetColormap(float t) {
    // Jet colormap: blue -> cyan -> green -> yellow -> red
    t = clamp(t, 0.0, 1.0);
    
    float r = clamp(1.5 - abs(4.0 * t - 3.0), 0.0, 1.0);
    float g = clamp(1.5 - abs(4.0 * t - 2.0), 0.0, 1.0);
    float b = clamp(1.5 - abs(4.0 * t - 1.0), 0.0, 1.0);
    
    return vec3(r, g, b);
}

void main() {
    vec3 color = jetColormap(luxValue);
    outColor = vec4(color, 1.0);
}
"""


def compile_shader(shader_type, source):
    """Compile a GLSL shader."""
    from OpenGL.GL import (
        glCreateShader, glShaderSource, glCompileShader,
        glGetShaderiv, glGetShaderInfoLog,
        GL_COMPILE_STATUS
    )
    
    shader = glCreateShader(shader_type)
    glShaderSource(shader, source)
    glCompileShader(shader)
    
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        error = glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader compilation error: {error}")
    
    return shader


def create_shader_program(vertex_source, fragment_source):
    """Create a shader program from vertex and fragment sources."""
    from OpenGL.GL import (
        glCreateProgram, glAttachShader, glLinkProgram,
        glGetProgramiv, glGetProgramInfoLog, glDeleteShader,
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_LINK_STATUS
    )
    
    vertex_shader = compile_shader(GL_VERTEX_SHADER, vertex_source)
    fragment_shader = compile_shader(GL_FRAGMENT_SHADER, fragment_source)
    
    program = glCreateProgram()
    glAttachShader(program, vertex_shader)
    glAttachShader(program, fragment_shader)
    glLinkProgram(program)
    
    if not glGetProgramiv(program, GL_LINK_STATUS):
        error = glGetProgramInfoLog(program).decode()
        raise RuntimeError(f"Shader linking error: {error}")
    
    glDeleteShader(vertex_shader)
    glDeleteShader(fragment_shader)
    
    return program
