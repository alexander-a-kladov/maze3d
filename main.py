#!/usr/bin/python3

import math
import sys
from pathlib import Path

import pygame
from OpenGL.GL import *
from OpenGL.GLU import *


BASE_DIR = Path(__file__).resolve().parent

FLOORS_DIR = BASE_DIR / "floors"
OBJECTS_DIR = BASE_DIR / "objects"
DOOR_OBJ_FILE = OBJECTS_DIR / "K.obj"
DOOR_MTL_FILE = OBJECTS_DIR / "K.mtl"

MAX_FLOORS = 2

WALL_TEXTURE_FILE = BASE_DIR / "textures" / "w.png"
FLOOR_TEXTURE_FILE = BASE_DIR / "textures" / "f.png"
FINISH_TEXTURE_FILE = BASE_DIR / "textures" / "e.png"

WALK_SOUND_FILE = BASE_DIR / "sounds" / "walk.wav"
DOOR_SOUND_FILE = BASE_DIR / "sounds" / "door.wav"
LIFT_SOUND_FILE = BASE_DIR / "sounds" / "lift.wav"
TAKE_SOUND_FILE = BASE_DIR / "sounds" / "take.wav"


# ============================================================
# ГЕОМЕТРИЯ
# ============================================================

CELL_SIZE = 2.0
FLOOR_LEVEL_HEIGHT = CELL_SIZE

# Куб пола:
#
#        Y=0
#   ─────────────  <- верхняя грань пола
#   │            │
#   │    ПОЛ     │
#   │            │
#   ─────────────
#       Y=-2
#
FLOOR_BOTTOM = -CELL_SIZE*0.1
FLOOR_TOP = 0.0

# Куб стены:
#
#       Y=2
#   ─────────────
#   │   СТЕНА    │
#   │            │
#   ─────────────  <- верхняя грань пола Y=0
#
WALL_BOTTOM = 0.0
WALL_TOP = CELL_SIZE
FLOOR_HEIGHT = CELL_SIZE * 0.1
RENDER_DISTANCE = 20.0 * CELL_SIZE
# ============================================================
# ИГРОК
# ============================================================

PLAYER_HEIGHT = 0.90
PLAYER_RADIUS = 0.22

MOVE_SPEED = 7.0
TURN_SPEED = 250.0

FOV = 70.0
NEAR = 0.05
FAR = 300.0

MOUSE_LOOK_SENSITIVITY = 0.18

HEAD_YAW_LIMIT = 35.0
HEAD_PITCH_LIMIT = 20.0

# Цвет неба
SKY_COLOR = (0.38, 0.65, 0.95, 1.0)

VERTEX_SHADER_SOURCE = """
#version 120

varying vec2 v_texcoord;

void main()
{
    v_texcoord = gl_MultiTexCoord0.st;

    gl_Position = gl_ModelViewProjectionMatrix
                * gl_Vertex;
}
"""


FRAGMENT_SHADER_SOURCE = """
#version 120

uniform sampler2D u_texture;
uniform float u_time;

varying vec2 v_texcoord;

void main()
{
    vec2 uv = v_texcoord;

    // Первая волна
    float wave1 = sin(
        uv.y * 18.0
        + u_time * 3.0
    ) * 0.025;

    // Вторая волна
    float wave2 = sin(
        uv.x * 15.0
        + u_time * 2.2
    ) * 0.025;

    // Небольшая диагональная волна
    float wave3 = sin(
        (uv.x + uv.y) * 22.0
        + u_time * 4.0
    ) * 0.012;

    uv.x += wave1 + wave3;
    uv.y += wave2 + wave3;

    vec4 color = texture2D(
        u_texture,
        uv
    );

    gl_FragColor = color;
}
"""

def create_shader_program(
    vertex_source,
    fragment_source
):

    vertex_shader = glCreateShader(
        GL_VERTEX_SHADER
    )

    glShaderSource(
        vertex_shader,
        vertex_source
    )

    glCompileShader(
        vertex_shader
    )

    if not glGetShaderiv(
        vertex_shader,
        GL_COMPILE_STATUS
    ):

        error = glGetShaderInfoLog(
            vertex_shader
        ).decode()

        raise RuntimeError(
            "Ошибка vertex shader:\n"
            + error
        )


    fragment_shader = glCreateShader(
        GL_FRAGMENT_SHADER
    )

    glShaderSource(
        fragment_shader,
        fragment_source
    )

    glCompileShader(
        fragment_shader
    )

    if not glGetShaderiv(
        fragment_shader,
        GL_COMPILE_STATUS
    ):

        error = glGetShaderInfoLog(
            fragment_shader
        ).decode()

        raise RuntimeError(
            "Ошибка fragment shader:\n"
            + error
        )


    program = glCreateProgram()

    glAttachShader(
        program,
        vertex_shader
    )

    glAttachShader(
        program,
        fragment_shader
    )

    glLinkProgram(
        program
    )

    if not glGetProgramiv(
        program,
        GL_LINK_STATUS
    ):

        error = glGetProgramInfoLog(
            program
        ).decode()

        raise RuntimeError(
            "Ошибка shader program:\n"
            + error
        )


    glDeleteShader(
        vertex_shader
    )

    glDeleteShader(
        fragment_shader
    )

    return program

# ============================================================
# ЗАГРУЗКА ЛАБИРИНТА
# ============================================================

def load_floors():

    floors = []

    total_starts = 0
    total_finishes = 0

    for level in range(100):

        filename = FLOORS_DIR / f"{level:02d}.txt"

        if not filename.exists():
            break

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:
            lines = file.read().splitlines()

        if not lines:
            raise ValueError(
                f"Файл {filename.name} пустой."
            )

        width = max(
            len(line)
            for line in lines
        )

        grid = [
            line.ljust(width)
            for line in lines
        ]

        height = len(grid)

        start = None
        finishes = []

        # Отдельный список объектов этажа
        objects = []

        # Копия карты, в которой k превращается в f
        clean_grid = [
            list(row)
            for row in grid
        ]

        for z, row in enumerate(grid):

            for x, ch in enumerate(row):

                if ch == "s":

                    if start is not None:
                        raise ValueError(
                            f"В файле {filename.name} "
                            "больше одной клетки 's'."
                        )

                    start = (x, z)

                elif ch == "e":

                    finishes.append(
                        (x, z)
                    )

                elif ch == "k":
                    # Ключ — отдельный объект.
                    # Под ним автоматически появляется пол.
                    clean_grid[z][x] = "f"

                    objects.append({
                        "type": "k",
                        "x": x,
                        "z": z
                    })

                elif ch == "K":
                    # Дверь — отдельный объект.
                    # Под дверью автоматически появляется пол.
                    clean_grid[z][x] = "f"

                    objects.append({
                        "type": "K",
                        "x": x,
                        "z": z
                    })

                elif ch == "l":
                    clean_grid[z][x] = " "

                    objects.append({
                        "type": "l",
                        "x": x,
                        "z": z,
                        "floor": level,
                        "initial_floor": level,
                        "initial_x": x,
                        "initial_z": z,
                        "moving": False,
                        "direction": 0,
                        "progress": 0.0,
                        "target_floor": level
                    })

        # Возвращаем строки обратно
        grid = [
            "".join(row)
            for row in clean_grid
        ]

        total_starts += (
            1 if start is not None else 0
        )

        total_finishes += len(finishes)

        floors.append({
            "grid": grid,
            "width": width,
            "height": height,
            "start": start,
            "finishes": finishes,

            # Объекты отдельно от лабиринта
            "objects": objects
        })

    if not floors:
        raise ValueError(
            "В каталоге floors нет файлов "
            "00.txt, 01.txt и т.д."
        )

    if total_starts != 1:
        raise ValueError(
            "Во всех этажах вместе должна быть "
            "ровно одна клетка 's'."
        )

    if total_finishes != 1:
        raise ValueError(
            "Во всех этажах вместе должна быть "
            "ровно одна клетка 'e'."
        )

    return floors

# ============================================================
# ТЕКСТУРЫ
# ============================================================

def make_checker_texture(
    color1,
    color2,
    size=64
):

    data = bytearray()

    for y in range(size):

        for x in range(size):

            if (
                (x // 8 + y // 8) % 2
                == 0
            ):
                color = color1
            else:
                color = color2

            data.extend(color)

    texture = glGenTextures(1)

    glBindTexture(
        GL_TEXTURE_2D,
        texture
    )

    glTexParameteri(
        GL_TEXTURE_2D,
        GL_TEXTURE_MIN_FILTER,
        GL_LINEAR
    )

    glTexParameteri(
        GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER,
        GL_LINEAR
    )

    glTexParameteri(
        GL_TEXTURE_2D,
        GL_TEXTURE_WRAP_S,
        GL_REPEAT
    )

    glTexParameteri(
        GL_TEXTURE_2D,
        GL_TEXTURE_WRAP_T,
        GL_REPEAT
    )

    glTexImage2D(
        GL_TEXTURE_2D,
        0,
        GL_RGB,
        size,
        size,
        0,
        GL_RGB,
        GL_UNSIGNED_BYTE,
        bytes(data)
    )

    return texture


def load_texture(
    path,
    fallback1,
    fallback2
):

    if not path.exists():

        print(
            f"Предупреждение: "
            f"{path} не найден."
        )

        return make_checker_texture(
            fallback1,
            fallback2
        )

    try:

        surface = pygame.image.load(
            str(path)
        ).convert_alpha()

        surface = pygame.transform.flip(
            surface,
            False,
            True
        )

        width, height = (
            surface.get_size()
        )

        data = pygame.image.tostring(
            surface,
            "RGBA",
            True
        )

        texture = glGenTextures(1)

        glBindTexture(
            GL_TEXTURE_2D,
            texture
        )

        glTexParameteri(
            GL_TEXTURE_2D,
            GL_TEXTURE_MIN_FILTER,
            GL_LINEAR_MIPMAP_LINEAR
        )

        glTexParameteri(
            GL_TEXTURE_2D,
            GL_TEXTURE_MAG_FILTER,
            GL_LINEAR
        )

        glTexParameteri(
            GL_TEXTURE_2D,
            GL_TEXTURE_WRAP_S,
            GL_REPEAT
        )

        glTexParameteri(
            GL_TEXTURE_2D,
            GL_TEXTURE_WRAP_T,
            GL_REPEAT
        )

        gluBuild2DMipmaps(
            GL_TEXTURE_2D,
            GL_RGBA,
            width,
            height,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            data
        )

        return texture

    except pygame.error as error:

        print(
            f"Ошибка загрузки "
            f"{path}: {error}"
        )

        return make_checker_texture(
            fallback1,
            fallback2
        )


# ============================================================
# ЗВУК
# ============================================================

def load_walk_sound(path):

    if not path.exists():

        print(
            f"Предупреждение: "
            f"{path} не найден."
        )

        return None

    try:

        return pygame.mixer.Sound(
            str(path)
        )

    except pygame.error as error:

        print(
            f"Ошибка загрузки "
            f"{path}: {error}"
        )

        return None

# =======
# Загрузка 3d-моделей
# =======

class OBJModel:

    def __init__(self, obj_file, mtl_file):
        self.obj_file = Path(obj_file)
        self.mtl_file = Path(mtl_file)

        self.vertices = []
        self.texcoords = []
        self.normals = []
        self.faces = []

        self.materials = {}
        self.current_material = None

        self.load_mtl()
        self.load_material_textures()
        self.load_obj()

    def load_mtl(self):
        if not self.mtl_file.exists():
            print(
                f"Предупреждение: не найден MTL: "
                f"{self.mtl_file}"
            )
            return

        self.current_material = None

        with open(
            self.mtl_file,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:
                line = line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                parts = line.split()

                if not parts:
                    continue

                command = parts[0]

                # ------------------------------------------------
                # Материал
                # ------------------------------------------------
                if command == "newmtl":

                    if len(parts) < 2:
                        continue

                    name = parts[1]

                    self.materials[name] = {
                        "Kd": (1.0, 1.0, 1.0),
                        "map_Kd": None,
                        "texture": None
                    }

                    self.current_material = name

                # ------------------------------------------------
                # Цвет материала
                # ------------------------------------------------
                elif command == "Kd":

                    if (
                        self.current_material is not None
                        and len(parts) >= 4
                    ):
                        self.materials[
                            self.current_material
                        ]["Kd"] = (
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3])
                        )

                # ------------------------------------------------
                # Текстура
                # ------------------------------------------------
                elif command == "map_Kd":

                    if (
                        self.current_material is not None
                        and len(parts) >= 2
                    ):
                        texture_name = " ".join(
                            parts[1:]
                        )

                        self.materials[
                            self.current_material
                        ]["map_Kd"] = texture_name

    def load_material_textures(self):
        for name, material in self.materials.items():

            texture_name = material.get("map_Kd")

            if not texture_name:
                continue

            texture_path = Path(texture_name)

            if not texture_path.is_absolute():
                texture_path = (
                    self.mtl_file.parent
                    / texture_path
                )

            if not texture_path.exists():
                print(
                    f"Предупреждение: текстура "
                    f"материала '{name}' не найдена: "
                    f"{texture_path}"
                )
                continue

            try:
                surface = pygame.image.load(
                    str(texture_path)
                ).convert_alpha()

                surface = pygame.transform.flip(
                    surface,
                    False,
                    True
                )

                width, height = surface.get_size()

                data = pygame.image.tostring(
                    surface,
                    "RGBA",
                    True
                )

                texture = glGenTextures(1)

                glBindTexture(
                    GL_TEXTURE_2D,
                    texture
                )

                glTexParameteri(
                    GL_TEXTURE_2D,
                    GL_TEXTURE_MIN_FILTER,
                    GL_LINEAR_MIPMAP_LINEAR
                )

                glTexParameteri(
                    GL_TEXTURE_2D,
                    GL_TEXTURE_MAG_FILTER,
                    GL_LINEAR
                )

                glTexParameteri(
                    GL_TEXTURE_2D,
                    GL_TEXTURE_WRAP_S,
                    GL_REPEAT
                )

                glTexParameteri(
                    GL_TEXTURE_2D,
                    GL_TEXTURE_WRAP_T,
                    GL_REPEAT
                )

                gluBuild2DMipmaps(
                    GL_TEXTURE_2D,
                    GL_RGBA,
                    width,
                    height,
                    GL_RGBA,
                    GL_UNSIGNED_BYTE,
                    data
                )

                material["texture"] = texture

                print(
                    f"Загружена текстура "
                    f"'{name}': {texture_path.name}"
                )

            except Exception as error:
                print(
                    f"Ошибка загрузки текстуры "
                    f"{texture_path}: {error}"
                )

                material["texture"] = None

        glBindTexture(
            GL_TEXTURE_2D,
            0
        )

    def load_obj(self):

        if not self.obj_file.exists():

            raise FileNotFoundError(
                f"Не найден OBJ: {self.obj_file}"
            )

        with open(
            self.obj_file,
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:

                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split()

                if not parts:
                    continue

                command = parts[0]

                if command == "v":

                    self.vertices.append(
                        (
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3])
                        )
                    )

                elif command == "vt":

                    self.texcoords.append(
                        (
                            float(parts[1]),
                            float(parts[2])
                        )
                    )

                elif command == "vn":

                    self.normals.append(
                        (
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3])
                        )
                    )

                elif command == "usemtl":

                    if len(parts) >= 2:

                        self.current_material = parts[1]

                elif command == "f":

                    face = []

                    for item in parts[1:]:

                        values = item.split("/")

                        vertex_index = int(
                            values[0]
                        )

                        texcoord_index = None
                        normal_index = None

                        if len(values) >= 2:

                            if values[1]:

                                texcoord_index = int(
                                    values[1]
                                )

                        if len(values) >= 3:

                            if values[2]:

                                normal_index = int(
                                    values[2]
                                )

                        face.append(
                            (
                                vertex_index,
                                texcoord_index,
                                normal_index
                            )
                        )

                    if len(face) >= 3:

                        self.faces.append(
                            (
                                face,
                                self.current_material
                            )
                        )

    def _index(self, index, length):

        if index is None:
            return None

        if index > 0:
            return index - 1

        return length + index

    def draw(
        self,
        x,
        y,
        z,
        scale=1.0,
        rotation=0.0
    ):
        glPushMatrix()

        glTranslatef(
            x,
            y,
            z
        )

        glRotatef(
            rotation,
            0.0,
            1.0,
            0.0
        )

        glScalef(
            scale,
            scale,
            scale
        )

        glEnable(
            GL_TEXTURE_2D
        )

        for face, material_name in self.faces:

            material = self.materials.get(
                material_name
            )

            texture = None

            if material is not None:

                r, g, b = material["Kd"]

                glColor3f(
                    r,
                    g,
                    b
                )

                texture = material.get(
                    "texture"
                )

            else:

                glColor3f(
                    1.0,
                    1.0,
                    1.0
                )

            # Текстура привязывается ДО glBegin().
            if texture is not None:
                glBindTexture(
                    GL_TEXTURE_2D,
                    texture
                )
            else:
                glBindTexture(
                    GL_TEXTURE_2D,
                    0
                )

            glBegin(
                GL_TRIANGLES
            )

            # Триангуляция полигона
            for i in range(
                1,
                len(face) - 1
            ):

                triangle = (
                    face[0],
                    face[i],
                    face[i + 1]
                )

                for (
                    vertex_index,
                    texcoord_index,
                    normal_index
                ) in triangle:

                    vertex_index = self._index(
                        vertex_index,
                        len(self.vertices)
                    )

                    # Нормаль
                    if normal_index is not None:

                        normal_index = self._index(
                            normal_index,
                            len(self.normals)
                        )

                        nx, ny, nz = (
                            self.normals[
                                normal_index
                            ]
                        )

                        glNormal3f(
                            nx,
                            ny,
                            nz
                        )

                    # UV
                    if (
                        texture is not None
                        and texcoord_index is not None
                    ):

                        texcoord_index = self._index(
                            texcoord_index,
                            len(self.texcoords)
                        )

                        u, v = (
                            self.texcoords[
                                texcoord_index
                            ]
                        )

                        glTexCoord2f(
                            u,
                            v
                        )

                    else:

                        glTexCoord2f(
                            0.0,
                            0.0
                        )

                    vx, vy, vz = (
                        self.vertices[
                            vertex_index
                        ]
                    )

                    glVertex3f(
                        vx,
                        vy,
                        vz
                    )

            glEnd()

        glBindTexture(
            GL_TEXTURE_2D,
            0
        )

        glColor3f(
            1.0,
            1.0,
            1.0
        )

        glPopMatrix()

# ============================================================
# ИГРА
# ============================================================

class MazeGame:

    def __init__(
        self,
        floors,
        wall_texture,
        floor_texture,
        finish_texture,
        walk_sound,
        take_sound
    ):

        self.floors = floors
        self.floor_count = len(floors)

        self.wall_texture = wall_texture
        self.floor_texture = floor_texture
        self.finish_texture = finish_texture

        self.objects = {}

        self.load_objects()

        self.initial_lifts = []

        for floor in self.floors:
            for obj in floor["objects"]:
                if obj["type"] == "l":
                    self.initial_lifts.append(
                        {
                            "floor": obj["floor"],
                            "x": obj["x"],
                            "z": obj["z"]
                        }
                    )

        self.lift_sound = None

        # Инвентарь игрока.
        # Формат: {"k": количество}
        self.inventory = {}
        self.walk_sound = walk_sound
        self.take_sound = take_sound
        self.walk_channel = None
        self.door_sound = None

        self.current_floor = 0

        self.grid = floors[0]["grid"]
        self.width = floors[0]["width"]
        self.height = floors[0]["height"]
        self.finishes = floors[0]["finishes"]

        self.finished = False

        self.object_rotation = 0.0

        self.wall_texture = (
            wall_texture
        )

        self.floor_texture = (
            floor_texture
        )

        self.finish_texture = (
            finish_texture
        )

        self.walk_sound = (
            walk_sound
        )

        self.walk_channel = None

        # Начальное направление:
        # вперёд по -Z.
        self.yaw = 0.0

        # Отдельное направление взгляда.
        # Оно НЕ влияет на направление движения.
        self.head_yaw = 0.0
        self.head_pitch = 0.0

        self.mouse_looking = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        start_floor = None
        start_position = None

        finish_position = None
        finish_floor = None

        for floor_index, floor in enumerate(floors):

            if floor["start"] is not None:

                start_floor = floor_index
                start_position = floor["start"]

            if floor["finishes"]:

                finish_floor = floor_index
                finish_position = floor["finishes"][0]

        if start_floor is None:
            raise ValueError(
                "Не найден старт 's'."
            )

        if finish_floor is None:
            raise ValueError(
                "Не найден финиш 's'."
            )

        self.current_floor = start_floor

        self.grid = floors[start_floor]["grid"]
        self.width = floors[start_floor]["width"]
        self.height = floors[start_floor]["height"]
        self.finishes = [
            finish_position
        ]
        self.finish_floor = finish_floor
        start_x, start_z = start_position

        self.x = (
            start_x * CELL_SIZE
            + CELL_SIZE / 2
        )

        self.z = (
            start_z * CELL_SIZE
            + CELL_SIZE / 2
        )

        self.finish_shader = create_shader_program(
            VERTEX_SHADER_SOURCE,
            FRAGMENT_SHADER_SOURCE
        )

        self.finish_shader_time = glGetUniformLocation(
            self.finish_shader,
            "u_time"
        )

        self.finish_shader_texture = glGetUniformLocation(
            self.finish_shader,
            "u_texture"
        )

    # =====
    # Загрузка 3d-объектов
    # =====

    def load_objects(self):
        object_files = {
            "k": (
                OBJECTS_DIR / "k.obj",
                OBJECTS_DIR / "k.mtl"
            ),
            "K": (
                DOOR_OBJ_FILE,
                DOOR_MTL_FILE
            ),
            "l": (
                OBJECTS_DIR / "l.obj",
                OBJECTS_DIR / "l.mtl"
            )
        }

        for symbol, (obj_file, mtl_file) in object_files.items():

            if not obj_file.exists():
                print(
                    f"Предупреждение: не найден объект {obj_file}"
                )
                continue

            try:
                self.objects[symbol] = OBJModel(
                    obj_file,
                    mtl_file
                )

                print(
                    f"Загружен объект '{symbol}': "
                    f"{obj_file.name}"
                )

            except Exception as error:
                print(
                    f"Ошибка загрузки объекта "
                    f"'{symbol}': {error}"
                )

    def draw_object(
        self,
        symbol,
        x,
        z
    ):
        model = self.objects.get(symbol)

        if model is None:
            return

        if not model.vertices:
            return

        min_y = min(
            v[1]
            for v in model.vertices
        )

        max_y = max(
            v[1]
            for v in model.vertices
        )

        object_height = max_y - min_y

        if object_height <= 0.000001:
            return

        target_height = CELL_SIZE * 0.5

        scale = target_height / object_height

        center_x = x + CELL_SIZE / 2
        center_z = z + CELL_SIZE / 2

        object_y = (
            self.floor_y()
            - min_y * scale
        )

        model.draw(
            center_x,
            object_y,
            center_z,
            scale,
            self.object_rotation
        )

    def draw_lift(
        self,
        obj,
        x,
        z,
        floor_index
    ):
        model = self.objects.get("l")

        if model is None:
            return

        if not model.vertices:
            return

        min_x = min(
            v[0]
            for v in model.vertices
        )

        max_x = max(
            v[0]
            for v in model.vertices
        )

        min_z = min(
            v[2]
            for v in model.vertices
        )

        max_z = max(
            v[2]
            for v in model.vertices
        )

        width = max_x - min_x
        depth = max_z - min_z

        horizontal_size = max(
            width,
            depth
        )

        if horizontal_size <= 0.000001:
            return

        scale = (
            CELL_SIZE
            / horizontal_size
        )

        center_x = (
            x + CELL_SIZE / 2
        )

        center_z = (
            z + CELL_SIZE / 2
        )

        min_y = min(
            v[1]
            for v in model.vertices
        )

        lift_y = (
            floor_index
            * FLOOR_LEVEL_HEIGHT
            + FLOOR_HEIGHT
            + obj["direction"]
            * obj["progress"]
            * FLOOR_LEVEL_HEIGHT
            - min_y * scale
        )

        model.draw(
            center_x,
            lift_y,
            center_z,
            scale,
            0.0
        )

    def draw_door(self, x, z):
        model = self.objects.get("K")

        if model is None:
            return

        min_y = min(
            vertex[1]
            for vertex in model.vertices
        )

        max_y = max(
            vertex[1]
            for vertex in model.vertices
        )

        object_height = max_y - min_y

        if object_height <= 0.000001:
            return

        # Дверь имеет высоту половины стены.
        target_height = CELL_SIZE

        scale = (
            target_height
            / object_height
        )

        center_x = (
            x + CELL_SIZE / 2
        )

        center_z = (
            z + CELL_SIZE / 2
        )

        object_y = (
            self.floor_y()
            - min_y * scale
        )

        rotation = self.get_door_rotation(
            int(x / CELL_SIZE),
            int(z / CELL_SIZE),
            self.grid
        )

        model.draw(
            center_x,
            object_y,
            center_z,
            scale,
            rotation
        )

    # ========================================================
    # КООРДИНАТЫ
    # ========================================================
    
    def floor_y(self):
        return (
            self.current_floor
            * FLOOR_LEVEL_HEIGHT
        )

    def get_player_lift(self):
        current_x = math.floor(
            self.x / CELL_SIZE
        )

        current_z = math.floor(
            self.z / CELL_SIZE
        )

        for obj in self.floors[
            self.current_floor
        ]["objects"]:

            if obj["type"] != "l":
                continue

            if (
                obj["x"] == current_x
                and
                obj["z"] == current_z
            ):
                return obj

        return None

    def get_player_lift(self):
        current_x = math.floor(
            self.x / CELL_SIZE
        )

        current_z = math.floor(
            self.z / CELL_SIZE
        )

        for obj in self.floors[
            self.current_floor
        ]["objects"]:

            if obj["type"] != "l":
                continue

            if (
                obj["x"] == current_x
                and
                obj["z"] == current_z
            ):
                return obj

        return None

    def change_floor(self, direction):
        lift = self.get_player_lift()

        if lift is None:
            return

        if lift["moving"]:
            return

        current_floor = lift["floor"]

        target_floor = (
            current_floor + direction
        )

        if (
            target_floor < 0
            or
            target_floor >= self.floor_count
        ):
            return

        current_x = lift["x"]
        current_z = lift["z"]

        target_grid = self.floors[
            target_floor
        ]["grid"]

        if (
            current_z < 0
            or current_z >= len(target_grid)
        ):
            return

        row = target_grid[current_z]

        if (
            current_x < 0
            or current_x >= len(row)
        ):
            return

        # Над / под лифтом не должно быть пола.
        if row[current_x] != " ":
            return

        lift["moving"] = True
        lift["direction"] = direction
        lift["progress"] = 0.0
        lift["target_floor"] = target_floor

        if self.lift_sound is not None:
            self.lift_sound.play()

    def get_door_rotation(self, x, z, grid):
        """
        Определяет ориентацию двери по стенам
        с двух противоположных сторон.

        Если стены слева и справа:
            дверь стоит поперёк X -> поворот 0 градусов.

        Если стены сверху и снизу:
            дверь стоит поперёк Z -> поворот 90 градусов.
        """

        width = len(grid[0]) if grid else 0
        height = len(grid)

        def cell(cx, cz):
            if (
                cz < 0
                or cz >= height
                or cx < 0
                or cx >= len(grid[cz])
            ):
                return "w"

            return grid[cz][cx]

        left = cell(x - 1, z) == "w"
        right = cell(x + 1, z) == "w"

        top = cell(x, z - 1) == "w"
        bottom = cell(x, z + 1) == "w"

        # Стены слева и справа.
        if left and right:
            return 90.0

        # Стены сверху и снизу.
        if top and bottom:
            return 0.0

        # Если однозначно определить нельзя,
        # оставляем стандартную ориентацию.
        return 0.0

    def cell_at_world(self, x, z):
        cx = math.floor(x / CELL_SIZE)
        cz = math.floor(z / CELL_SIZE)

        # Лифт является реальной проходимой клеткой,
        # даже если исходная карта в этой координате содержит " ".
        for obj in self.floors[
            self.current_floor
        ]["objects"]:

            if obj["type"] != "l":
                continue

            if (
                obj["x"] == cx
                and
                obj["z"] == cz
            ):
                return "l"

        if (
            cz < 0
            or cz >= len(self.grid)
            or cx < 0
            or cx >= len(self.grid[cz])
        ):
            return "w"

        return self.grid[cz][cx]

    def is_wall(
        self,
        cx,
        cz
    ):

        if cx < 0 or cz < 0:
            return True

        if (
            cx >= self.width
            or cz >= self.height
        ):
            return True

        return (
            self.grid[cz][cx]
            == "w"
        )

    def has_wall_between(self, x1, z1, x2, z2, grid):
        """
        Проверяет, пересекает ли отрезок от (x1,z1) до (x2,z2)
        клетку со стеной 'w' или финишем 'e'.

        Координаты x/z — мировые.
        """

        dx = x2 - x1
        dz = z2 - z1

        distance = math.sqrt(dx * dx + dz * dz)

        if distance <= 0.0001:
            return False

        # Шаг примерно 1/4 клетки.
        step = CELL_SIZE * 0.25

        steps = max(
            1,
            int(math.ceil(distance / step))
        )

        for i in range(1, steps):
            t = i / steps

            px = x1 + dx * t
            pz = z1 + dz * t

            cx = math.floor(px / CELL_SIZE)
            cz = math.floor(pz / CELL_SIZE)

            if (
                cz < 0
                or cz >= len(grid)
                or cx < 0
                or cx >= len(grid[cz])
            ):
                continue

            cell = grid[cz][cx]

            if cell == "w" or cell == "e":
                return True

        return False

    def is_visible_from_player(self, world_x, world_z):
        dx = world_x - self.x
        dz = world_z - self.z

        distance = math.sqrt(dx * dx + dz * dz)

        if distance > RENDER_DISTANCE:
            return False

        # Если совсем рядом — всегда рисуем
        if distance < CELL_SIZE * 2:
            return True

        # Направление от игрока к объекту
        target_angle = math.degrees(math.atan2(dx, -dz))

        # Разница относительно направления взгляда
        angle_diff = (target_angle - self.yaw + 180) % 360 - 180

        # 100 градусов в каждую сторону
        return abs(angle_diff) <= 100

    def is_finish(
        self,
        cx,
        cz
    ):

        if cx < 0 or cz < 0:
            return False

        if (
            cx >= self.width
            or cz >= self.height
        ):
            return False

        return (
            self.grid[cz][cx]
            == "e"
        )

    def cell_is_visible(self, x, z, grid):
        center_x = x + CELL_SIZE / 2
        center_z = z + CELL_SIZE / 2

        # Очень близкие клетки всегда рисуем.
        dx = center_x - self.x
        dz = center_z - self.z

        if dx * dx + dz * dz < (CELL_SIZE * 2) ** 2:
            return True

        return not self.has_wall_between(
            self.x,
            self.z,
            center_x,
            center_z,
            grid
        )

    def object_is_visible(self, x, z, grid):
        points = (
            (x + CELL_SIZE * 0.25, z + CELL_SIZE * 0.25),
            (x + CELL_SIZE * 0.75, z + CELL_SIZE * 0.25),
            (x + CELL_SIZE * 0.25, z + CELL_SIZE * 0.75),
            (x + CELL_SIZE * 0.75, z + CELL_SIZE * 0.75),
            (x + CELL_SIZE * 0.50, z + CELL_SIZE * 0.50),
        )

        for px, pz in points:

            if not self.has_wall_between(
                self.x,
                self.z,
                px,
                pz,
                grid
            ):
                return True

        return False

    # ========================================================
    # СТОЛКНОВЕНИЯ
    # ========================================================

    def is_door_at(self, x, z):
        floor = self.floors[self.current_floor]

        cell_x = math.floor(
            x / CELL_SIZE
        )

        cell_z = math.floor(
            z / CELL_SIZE
        )

        for obj in floor["objects"]:
            if obj["type"] != "K":
                continue

            if (
                obj["x"] == cell_x
                and obj["z"] == cell_z
            ):
                return True

        return False

    def can_stand(
        self,
        x,
        z
    ):

        r = PLAYER_RADIUS

        points = (
            (x - r, z - r),
            (x + r, z - r),
            (x - r, z + r),
            (x + r, z + r),

            (x, z - r),
            (x, z + r),

            (x - r, z),
            (x + r, z),
        )

        for px, pz in points:

            if self.is_door_at(px, pz):
                return False

            cell = self.cell_at_world(
                px,
                pz
            )

            if cell == "w" or cell == "e" or cell == " ":
                return False

        return True

    def touches_finish(
        self,
        x,
        z
    ):

        r = PLAYER_RADIUS

        points = (
            (x - r, z - r),
            (x + r, z - r),
            (x - r, z + r),
            (x + r, z + r),

            (x, z - r),
            (x, z + r),

            (x - r, z),
            (x + r, z),
        )

        for px, pz in points:

            if self.cell_at_world(
                px,
                pz
            ) == "e":

                return True

        return False

    # ========================================================
    # ДВИЖЕНИЕ
    # ========================================================

    def try_move(
        self,
        amount
    ):

        angle = math.radians(
            self.yaw
        )

        dx = (
            math.sin(angle)
            * amount
        )

        dz = (
            -math.cos(angle)
            * amount
        )

        old_x = self.x
        old_z = self.z

        # ========================================================
        # ДВИЖЕНИЕ ПО X
        # ========================================================

        next_x = self.x + dx

        # Если игрок касается финиша —
        # завершаем игру, но внутрь куба не заходим.
        if self.touches_finish(
            next_x,
            self.z
        ):

            self.finished = True

            if self.walk_channel is not None:
                self.walk_channel.stop()
                self.walk_channel = None

            return False

        if self.can_stand(
            next_x,
            self.z
        ):

            self.x = next_x

        # ========================================================
        # ДВИЖЕНИЕ ПО Z
        # ========================================================

        next_z = self.z + dz

        if self.touches_finish(
            self.x,
            next_z
        ):

            self.finished = True

            if self.walk_channel is not None:
                self.walk_channel.stop()
                self.walk_channel = None

            return False

        if self.can_stand(
            self.x,
            next_z
        ):

            self.z = next_z

        moved = (
            abs(self.x - old_x)
            +
            abs(self.z - old_z)
        ) > 0.000001

        return moved


    def check_finish(self):

        if self.cell_at_world(
            self.x,
            self.z
        ) == "e":

            self.finished = True



    # ========================================================
    # UPDATE
    # ========================================================

    def update(self, dt, keys):
        self.object_rotation += 90.0 * dt

        if self.object_rotation >= 360.0:
            self.object_rotation -= 360.0

        if self.finished:

            # На всякий случай останавливаем шаги
            if self.walk_channel is not None:
                self.walk_channel.stop()
                self.walk_channel = None

            return

        # ========================================================
        # АНИМАЦИЯ ЛИФТОВ
        # ========================================================

        LIFT_SPEED = 2.5

        for floor in self.floors:
            for lift in floor["objects"][:]:

                if lift["type"] != "l":
                    continue

                if not lift["moving"]:
                    continue

                lift["progress"] += (
                    dt * LIFT_SPEED
                )

                if lift["progress"] < 1.0:
                    continue

                # Переезд завершён.
                lift["progress"] = 1.0

                old_floor = lift["floor"]
                new_floor = lift["target_floor"]

                old_objects = self.floors[
                    old_floor
                ]["objects"]

                if lift in old_objects:
                    old_objects.remove(lift)

                lift["floor"] = new_floor
                lift["moving"] = False
                lift["direction"] = 0
                lift["progress"] = 0.0
                lift["target_floor"] = new_floor

                self.floors[
                    new_floor
                ]["objects"].append(lift)

                # Игрок приезжает вместе с лифтом.
                self.current_floor = new_floor

                self.grid = self.floors[
                    new_floor
                ]["grid"]

                self.width = self.floors[
                    new_floor
                ]["width"]

                self.height = self.floors[
                    new_floor
                ]["height"]

        # --------------------------------------------------------
        # Поворот
        # --------------------------------------------------------

        if keys[pygame.K_a]:
            self.yaw -= TURN_SPEED * dt

        if keys[pygame.K_d]:
            self.yaw += TURN_SPEED * dt


        # --------------------------------------------------------
        # Движение
        # --------------------------------------------------------

        movement = 0.0

        if keys[pygame.K_w]:
            movement += MOVE_SPEED * dt

        if keys[pygame.K_s]:
            movement -= MOVE_SPEED * dt


        # Игрок не нажимает W/S
        if movement == 0.0:

            if self.walk_channel is not None:
                self.walk_channel.stop()
                self.walk_channel = None

            return


        # --------------------------------------------------------
        # Пытаемся двигаться
        # --------------------------------------------------------

        moved = self.try_move(movement)


        # --------------------------------------------------------
        # Звук шагов
        # --------------------------------------------------------

        if moved:

            if (
                self.walk_sound
                and (
                    self.walk_channel is None
                    or not self.walk_channel.get_busy()
                )
            ):

                self.walk_channel = (
                    self.walk_sound.play()
                )

        else:

            # Игрок упёрся в стену —
            # звук шагов тоже останавливаем.

            if self.walk_channel is not None:
                self.walk_channel.stop()
                self.walk_channel = None
        
        


    # ========================================================
    # КУБ
    # ========================================================

    def draw_cube(
        self,
        x0,
        y0,
        z0,
        x1,
        y1,
        z1,
        texture,
        shader=None
    ):

        glEnable(GL_TEXTURE_2D)

        glBindTexture(
            GL_TEXTURE_2D,
            texture
        )

        if shader is not None:

            glUseProgram(shader)

            time_location = glGetUniformLocation(
                shader,
                "u_time"
            )

            texture_location = glGetUniformLocation(
                shader,
                "u_texture"
            )

            glUniform1f(
                time_location,
                pygame.time.get_ticks() / 1000.0
            )

            glUniform1i(
                texture_location,
                0
            )

        glColor3f(
            1.0,
            1.0,
            1.0
        )

        glBegin(GL_QUADS)

        # FRONT
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x0, y0, z0)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x1, y0, z0)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x1, y1, z0)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x0, y1, z0)


        # BACK
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x1, y0, z1)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x0, y0, z1)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x0, y1, z1)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x1, y1, z1)


        # LEFT
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x0, y0, z1)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x0, y0, z0)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x0, y1, z0)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x0, y1, z1)


        # RIGHT
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x1, y0, z0)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x1, y0, z1)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x1, y1, z1)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x1, y1, z0)


        # TOP
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x0, y1, z0)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x1, y1, z0)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x1, y1, z1)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x0, y1, z1)


        # BOTTOM
        glTexCoord2f(0.0, 0.0)
        glVertex3f(x0, y0, z1)

        glTexCoord2f(1.0, 0.0)
        glVertex3f(x1, y0, z1)

        glTexCoord2f(1.0, 1.0)
        glVertex3f(x1, y0, z0)

        glTexCoord2f(0.0, 1.0)
        glVertex3f(x0, y0, z0)

        glEnd()

        if shader is not None:

            glUseProgram(0)

    # ========================================================
    # ПОЛ
    # ========================================================

    def draw_floor_cube(self, x, z):

        y = self.floor_y()

        self.draw_cube(
            x,
            y + FLOOR_BOTTOM,
            z,
            x + CELL_SIZE,
            y + FLOOR_HEIGHT,
            z + CELL_SIZE,
            self.floor_texture
        )


    # ========================================================
    # СТЕНА
    # ========================================================

    def draw_wall_cube(self, x, z):

        y = self.floor_y()

        self.draw_cube(
            x,
            y + WALL_BOTTOM,
            z,
            x + CELL_SIZE,
            y + WALL_TOP,
            z + CELL_SIZE,
            self.wall_texture
        )


    # ========================================================
    # ФИНИШ
    # ========================================================
    
    def draw_finish_cube(self, x, z):

        y = self.floor_y()

        self.draw_cube(
            x,
            y + WALL_BOTTOM,
            z,
            x + CELL_SIZE,
            y + WALL_TOP,
            z + CELL_SIZE,
            self.finish_texture,
            self.finish_shader
        )

    # ========================================================
    # НЕБО
    # ========================================================

    def draw_sky_ceiling(self):

        sky_y = WALL_TOP + 0.01

        x1 = (
            self.width
            * CELL_SIZE
        )

        z1 = (
            self.height
            * CELL_SIZE
        )

        glDisable(
            GL_TEXTURE_2D
        )

        glColor4f(
            *SKY_COLOR
        )

        glBegin(GL_QUADS)

        glVertex3f(
            0,
            sky_y,
            0
        )

        glVertex3f(
            x1,
            sky_y,
            0
        )

        glVertex3f(
            x1,
            sky_y,
            z1
        )

        glVertex3f(
            0,
            sky_y,
            z1
        )

        glEnd()

        glColor4f(
            1,
            1,
            1,
            1
        )

        glEnable(
            GL_TEXTURE_2D
        )

#####
# Взятие предмета
#####

    def pickup_object(self):
        """
        Подбирает ближайший объект в текущем этаже.
        Сейчас поддерживается объект типа 'k'.
        """

        pickup_distance = CELL_SIZE * 0.8

        player_x = self.x
        player_z = self.z

        floor = self.floors[self.current_floor]

        for obj in floor["objects"]:
            if obj["type"] != "k":
                continue

            object_x = (
                obj["x"] * CELL_SIZE
                + CELL_SIZE / 2
            )

            object_z = (
                obj["z"] * CELL_SIZE
                + CELL_SIZE / 2
            )

            dx = object_x - player_x
            dz = object_z - player_z

            distance = math.sqrt(
                dx * dx + dz * dz
            )

            if distance <= pickup_distance:

                item_type = obj["type"]

                # Добавляем в инвентарь.
                self.inventory[item_type] = (
                    self.inventory.get(item_type, 0) + 1
                )


                if self.take_sound is not None:
                    self.take_sound.play()

                # Удаляем предмет с карты.
                floor["objects"].remove(obj)

                return True

        return False

    def open_door(self):
        """
        Открывает ближайшую дверь K, если есть ключ k.
        """

        if self.inventory.get("k", 0) <= 0:
            return False

        pickup_distance = CELL_SIZE * 0.8

        player_x = self.x
        player_z = self.z

        floor = self.floors[self.current_floor]

        for obj in floor["objects"]:
            if obj["type"] != "K":
                continue

            door_x = (
                obj["x"] * CELL_SIZE
                + CELL_SIZE / 2
            )

            door_z = (
                obj["z"] * CELL_SIZE
                + CELL_SIZE / 2
            )

            dx = door_x - player_x
            dz = door_z - player_z

            distance = math.sqrt(
                dx * dx + dz * dz
            )

            if distance <= pickup_distance:
                # Тратим один ключ
                self.inventory["k"] -= 1

                if self.inventory["k"] <= 0:
                    del self.inventory["k"]

                # Удаляем дверь с этажа
                floor["objects"].remove(obj)

                # Звук открытия
                if self.door_sound is not None:
                    self.door_sound.play()

                return True

        return False

    # ========================================================
    # ОТРИСОВКА ЛАБИРИНТА
    # ========================================================

    def draw_world(self):

        saved_floor = self.current_floor
        countm = 0
        counto = 0

        for floor_index, floor in enumerate(self.floors):

            self.current_floor = floor_index

            grid = floor["grid"]

            # ================================================
            # ЛАБИРИНТ
            # ================================================

            for z, row in enumerate(grid):
                for x, ch in enumerate(row):

                    world_x = x * CELL_SIZE
                    world_z = z * CELL_SIZE

                    # ------------------------------------------------
                    # СТЕНА
                    # ------------------------------------------------
                    if ch == "w":

                        # Для стен используем только дальность и угол обзора.
                        # Не используем occlusion по центру клетки.
                        if self.is_visible_from_player(
                            world_x + CELL_SIZE / 2,
                            world_z + CELL_SIZE / 2
                        ):
                            countm += 1
                            self.draw_wall_cube(
                                world_x,
                                world_z
                            )

                    # ------------------------------------------------
                    # ФИНИШ
                    # ------------------------------------------------
                    elif ch == "e":

                        if self.is_visible_from_player(
                            world_x + CELL_SIZE / 2,
                            world_z + CELL_SIZE / 2
                        ):
                            countm += 1
                            self.draw_finish_cube(
                                world_x,
                                world_z
                            )

                    # ------------------------------------------------
                    # ПОЛ
                    # ------------------------------------------------
                    elif ch == "f" or ch == "s":

                        if self.cell_is_visible(
                            world_x,
                            world_z,
                            grid
                        ):
                            countm += 1
                            self.draw_floor_cube(
                                world_x,
                                world_z
                            )

            # ================================================
            # ОБЪЕКТЫ
            # ================================================

            for obj in floor["objects"]:

                world_x = obj["x"] * CELL_SIZE
                world_z = obj["z"] * CELL_SIZE

                if not self.object_is_visible(
                    world_x,
                    world_z,
                    grid
                ):
                    continue

                counto += 1

                # ------------------------------------------------
                # КЛЮЧ
                # ------------------------------------------------
                if obj["type"] == "k":

                    self.draw_object(
                        "k",
                        world_x,
                        world_z
                    )

                # ------------------------------------------------
                # ДВЕРЬ
                # ------------------------------------------------
                elif obj["type"] == "K":

                    self.draw_door(
                        world_x,
                        world_z
                    )

                # ------
                # ЛИФТ
                # ------
                elif obj["type"] == "l":
                    world_x = obj["x"] * CELL_SIZE
                    world_z = obj["z"] * CELL_SIZE

                    if not self.object_is_visible(
                        world_x,
                        world_z,
                        grid
                    ):
                        continue

                    counto += 1

                    self.draw_lift(
                        obj,
                        world_x,
                        world_z,
                        obj["floor"]
                    )

        self.current_floor = saved_floor
        #print(countm, counto)

        #self.draw_sky_ceiling()


# ============================================================
# OPENGL
# ============================================================

def setup_opengl(width, height):

    glViewport(
        0,
        0,
        width,
        height
    )

    glEnable(GL_DEPTH_TEST)

    glEnable(GL_TEXTURE_2D)

    # ВАЖНО:
    # не отбрасываем ни внешние,
    # ни внутренние поверхности.
    glDisable(GL_CULL_FACE)

    glEnable(GL_BLEND)

    glBlendFunc(
        GL_SRC_ALPHA,
        GL_ONE_MINUS_SRC_ALPHA
    )

    glClearColor(
        *SKY_COLOR
    )

    glMatrixMode(GL_PROJECTION)

    glLoadIdentity()

    gluPerspective(
        FOV,
        width / max(height, 1),
        NEAR,
        FAR
    )

    glMatrixMode(GL_MODELVIEW)



# ============================================================
# РЕНДЕР
# ============================================================

def render(
    game,
    width,
    height
):

    glClear(
        GL_COLOR_BUFFER_BIT
        |
        GL_DEPTH_BUFFER_BIT
    )

    glMatrixMode(
        GL_PROJECTION
    )

    glLoadIdentity()

    gluPerspective(
        FOV,
        width / max(height, 1),
        NEAR,
        FAR
    )

    glMatrixMode(
        GL_MODELVIEW
    )

    glLoadIdentity()


    # ========================================================
    # Направление тела / движения
    # ========================================================

    body_angle = math.radians(
        game.yaw
    )


    # ========================================================
    # Направление взгляда
    # ========================================================

    view_yaw = (
        game.yaw
        + game.head_yaw
    )

    view_angle = math.radians(
        view_yaw
    )

    look_x = (
        game.x
        + math.sin(view_angle)
        * math.cos(
            math.radians(
                game.head_pitch
            )
        )
    )

    look_y = (
        PLAYER_HEIGHT
        + math.sin(
            math.radians(
                game.head_pitch
            )
        )
    )

    look_z = (
        game.z
        - math.cos(view_angle)
        * math.cos(
            math.radians(
                game.head_pitch
            )
        )
    )

    camera_y = (
        game.floor_y()
        + PLAYER_HEIGHT
    )

    player_lift = game.get_player_lift()

    if (
        player_lift is not None
        and player_lift["moving"]
    ):
        camera_y += (
            player_lift["direction"]
            * player_lift["progress"]
            * FLOOR_LEVEL_HEIGHT
        )

    # ========================================================
    # Камера
    # ========================================================
    
    pitch_angle = math.radians(game.head_pitch)
    gluLookAt(

        game.x,
        camera_y,
        game.z,

        look_x,
        camera_y + math.sin(pitch_angle),
        look_z,

        0,
        1,
        0
    )


    game.draw_world()


# ============================================================
# СБРОС ИГРЫ
# ============================================================

def reset_game(game):

    start_floor = None
    start_position = None

    for floor_index, floor in enumerate(game.floors):

        if floor["start"] is not None:

            start_floor = floor_index
            start_position = floor["start"]

            break

    if start_floor is None:
        return

    # --------------------------------------------------------
    # Возвращаем этаж старта
    # --------------------------------------------------------

    game.current_floor = start_floor

    game.grid = game.floors[
        start_floor
    ]["grid"]

    game.width = game.floors[
        start_floor
    ]["width"]

    game.height = game.floors[
        start_floor
    ]["height"]

    # --------------------------------------------------------
    # Возвращаем все лифты на исходные позиции
    # --------------------------------------------------------

    for floor in game.floors:
        floor["objects"] = [
            obj
            for obj in floor["objects"]
            if obj["type"] != "l"
        ]

    for initial_lift in game.initial_lifts:
        game.floors[
            initial_lift["floor"]
        ]["objects"].append({
            "type": "l",
            "x": initial_lift["x"],
            "z": initial_lift["z"],
            "floor": initial_lift["floor"],
            "initial_floor": initial_lift["floor"],
            "initial_x": initial_lift["x"],
            "initial_z": initial_lift["z"],
            "moving": False,
            "direction": 0,
            "progress": 0.0,
            "target_floor": initial_lift["floor"]
        })

    # --------------------------------------------------------
    # Возвращаем позицию игрока
    # --------------------------------------------------------

    sx, sz = start_position

    game.x = (
        sx * CELL_SIZE
        + CELL_SIZE / 2
    )

    game.z = (
        sz * CELL_SIZE
        + CELL_SIZE / 2
    )

    # --------------------------------------------------------
    # Камера
    # --------------------------------------------------------

    game.yaw = 0.0
    game.head_yaw = 0.0
    game.head_pitch = 0.0
    game.mouse_looking = False

    # --------------------------------------------------------
    # Состояние игры
    # --------------------------------------------------------

    game.finished = False
    game.inventory.clear()
    # --------------------------------------------------------
    # Останавливаем звук шагов
    # --------------------------------------------------------

    if game.walk_channel is not None:

        game.walk_channel.stop()
        game.walk_channel = None


def draw_fps(clock, font):
    """Рендерит FPS в текстуру и отображает поверх OpenGL сцены"""
    # 1. Считаем FPS и создаем Surface с текстом
    fps_text = f"FPS: {int(clock.get_fps())}"
    text_surface = font.render(fps_text, True, (255, 255, 0, 255)) # Желтый текст
    text_data = pygame.image.tostring(text_surface, "RGBA", True)
    width, height = text_surface.get_size()

    # 2. Переключаемся в 2D-режим (Ортографическая проекция)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    # Настраиваем плоскость под размеры окна (замените 800 и 600 на ваши переменные)
    glOrtho(0, 800, 0, 600, -1, 1)
    
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    # 3. Настройка параметров OpenGL для текста
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_TEXTURE_2D)

    # Создаем и привязываем текстуру
    texture_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    # 4. Рисуем квадрат с текстурой в левом верхнем углу (y = 560 при высоте окна 600)
    x, y = 10, 560 
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex2f(x, y)
    glTexCoord2f(1.0, 0.0); glVertex2f(x + width, y)
    glTexCoord2f(1.0, 1.0); glVertex2f(x + width, y + height)
    glTexCoord2f(0.0, 1.0); glVertex2f(x, y + height)
    glEnd()

    # 5. Очищаем ресурсы и возвращаем настройки 3D
    glDeleteTextures([texture_id])
    glDisable(GL_TEXTURE_2D)
    glDisable(GL_BLEND)
    
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

def draw_inventory(self, width, height):
    count = self.inventory.get("k", 0)

    if count <= 0:
        return

    model = self.objects.get("k")

    if model is None or not model.vertices:
        return

    # --------------------------------------------------------
    # Размер модели
    # --------------------------------------------------------

    min_x = min(v[0] for v in model.vertices)
    max_x = max(v[0] for v in model.vertices)

    min_y = min(v[1] for v in model.vertices)
    max_y = max(v[1] for v in model.vertices)

    min_z = min(v[2] for v in model.vertices)
    max_z = max(v[2] for v in model.vertices)

    size_x = max_x - min_x
    size_y = max_y - min_y
    size_z = max_z - min_z

    model_size = max(
        size_x,
        size_y,
        size_z
    )

    if model_size <= 0.000001:
        return

    # --------------------------------------------------------
    # HUD
    # --------------------------------------------------------

    icon_size = 64
    margin = 15

    icon_x = margin
    icon_y = margin

    # --------------------------------------------------------
    # Сохраняем 3D-состояние
    # --------------------------------------------------------

    glMatrixMode(GL_PROJECTION)
    glPushMatrix()

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()

    # --------------------------------------------------------
    # Небольшая 3D-сцена для иконки
    # --------------------------------------------------------

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()

    glOrtho(
        0,
        width,
        0,
        height,
        -100,
        100
    )

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glDisable(GL_DEPTH_TEST)

    # --------------------------------------------------------
    # Центрируем модель в квадрате HUD
    # --------------------------------------------------------

    glTranslatef(
        icon_x + icon_size * 0.5,
        icon_y + icon_size * 0.5,
        0.0
    )

    hud_scale = (
        icon_size * 0.75
        / model_size
    )

    glScalef(
        hud_scale,
        hud_scale,
        hud_scale
    )

    # Центр модели по всем осям
    center_model_x = (
        min_x + max_x
    ) * 0.5

    center_model_y = (
        min_y + max_y
    ) * 0.5

    center_model_z = (
        min_z + max_z
    ) * 0.5

    glTranslatef(
        -center_model_x,
        -center_model_y,
        -center_model_z
    )

    # Небольшой постоянный поворот,
    # чтобы объект было лучше видно.
    glRotatef(
        25.0,
        1.0,
        0.0,
        0.0
    )

    glRotatef(
        self.object_rotation,
        0.0,
        1.0,
        0.0
    )

    model.draw(
        0.0,
        0.0,
        0.0,
        1.0,
        0.0
    )

    # --------------------------------------------------------
    # Восстанавливаем 2D/HUD состояние
    # --------------------------------------------------------

    glEnable(GL_DEPTH_TEST)

    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()

    glMatrixMode(GL_PROJECTION)
    glPopMatrix()

    glMatrixMode(GL_MODELVIEW)

    # --------------------------------------------------------
    # Количество
    # --------------------------------------------------------

    # Здесь рисуем количество обычным pygame-шрифтом
    # поверх OpenGL HUD.

# ============================================================
# MAIN
# ============================================================

def main():

    pygame.init()

    try:

        pygame.mixer.init()

    except pygame.error:

        print(
            "Аудиоподсистема недоступна."
        )


    width = 1280
    height = 720


    screen = pygame.display.set_mode(

        (
            width,
            height
        ),

        pygame.DOUBLEBUF
        |
        pygame.OPENGL
        |
        pygame.RESIZABLE
    )


    pygame.display.set_caption(
        "Maze OpenGL"
    )


    # --------------------------------------------------------
    # Лабиринт
    # --------------------------------------------------------

    floors = load_floors()



    # --------------------------------------------------------
    # Текстуры
    # --------------------------------------------------------

    wall_texture = load_texture(

        WALL_TEXTURE_FILE,

        (180, 180, 180),
        (100, 100, 100)
    )


    floor_texture = load_texture(

        FLOOR_TEXTURE_FILE,

        (170, 170, 170),
        (100, 100, 100)
    )


    finish_texture = load_texture(

        FINISH_TEXTURE_FILE,

        (255, 220, 40),
        (180, 120, 20)
    )


    walk_sound = load_walk_sound(
        WALK_SOUND_FILE
    )

    door_sound = load_walk_sound(
        DOOR_SOUND_FILE
    )

    lift_sound = load_walk_sound(
        LIFT_SOUND_FILE
    )

    take_sound = load_walk_sound(
        TAKE_SOUND_FILE
    )

    setup_opengl(
        width,
        height
    )


    game = MazeGame(
        floors,
        wall_texture,
        floor_texture,
        finish_texture,
        walk_sound,
        take_sound
    )

    game.door_sound = door_sound
    game.lift_sound = lift_sound


    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)

    running = True


    while running:

        dt = min(
            clock.tick(120)
            / 1000.0,
            0.05
        )


        # ====================================================
        # СОБЫТИЯ
        # ====================================================

        for event in pygame.event.get():

            if (
                event.type
                == pygame.QUIT
            ):

                running = False


            elif (
                event.type
                == pygame.KEYDOWN
            ):

                if (
                    event.key
                    == pygame.K_ESCAPE
                ):

                    running = False


                elif (
                    event.key
                    == pygame.K_r
                    and game.finished
                ):

                    reset_game(
                        game
                    )

                elif event.key == pygame.K_q:

                    game.change_floor(+1)

                elif event.key == pygame.K_z:

                    game.change_floor(-1)

                elif event.key == pygame.K_e:
                    if not game.open_door():
                        game.pickup_object()

            elif (
                event.type
                == pygame.VIDEORESIZE
            ):

                width = max(
                    320,
                    event.w
                )

                height = max(
                    240,
                    event.h
                )


                pygame.display.set_mode(

                    (
                        width,
                        height
                    ),

                    pygame.DOUBLEBUF
                    |
                    pygame.OPENGL
                    |
                    pygame.RESIZABLE
                )


                setup_opengl(
                    width,
                    height
                )

            elif event.type == pygame.MOUSEBUTTONDOWN:

                if event.button == 1:

                    game.mouse_looking = True
                    game.last_mouse_x = event.pos[0]
                    game.last_mouse_y = event.pos[1]


            elif event.type == pygame.MOUSEBUTTONUP:

                if event.button == 1:

                    game.mouse_looking = False
                    # Возвращаем взгляд в исходное положение
                    game.head_yaw = 0.0
                    game.head_pitch = 0.0


            elif event.type == pygame.MOUSEMOTION:

                if game.mouse_looking:

                    mouse_x, mouse_y = event.pos

                    dx = (
                        mouse_x
                        - game.last_mouse_x
                    )

                    dy = (
                        mouse_y
                        - game.last_mouse_y
                    )

                    game.last_mouse_x = mouse_x
                    game.last_mouse_y = mouse_y


                    # Горизонтальный поворот головы

                    game.head_yaw += (
                        dx
                        * MOUSE_LOOK_SENSITIVITY
                    )


                    # Вертикальный поворот головы

                    game.head_pitch -= (
                        dy
                        * MOUSE_LOOK_SENSITIVITY
                    )


                    # Ограничение влево/вправо

                    game.head_yaw = max(
                        -HEAD_YAW_LIMIT,
                        min(
                            HEAD_YAW_LIMIT,
                            game.head_yaw
                        )
                    )


                    # Ограничение вверх/вниз

                    game.head_pitch = max(
                        -HEAD_PITCH_LIMIT,
                        min(
                            HEAD_PITCH_LIMIT,
                            game.head_pitch
                        )
                    )


        # ====================================================
        # ИГРОВАЯ ЛОГИКА
        # ====================================================

        keys = pygame.key.get_pressed()

        game.update(
            dt,
            keys
        )


        # ====================================================
        # РЕНДЕР
        # ====================================================

        render(
            game,
            width,
            height
        )
        
        draw_fps(clock, font)


        draw_inventory(
            game,
            width,
            height
        )

        pygame.display.flip()

        clock.tick(60)

        # Заголовок окна.

        if game.finished:

            pygame.display.set_caption(

                "Maze OpenGL — "
                "ИГРА ЗАКОНЧЕНА! "
                "| R — рестарт "
                "| ESC — выход"
            )

        else:

            pygame.display.set_caption(

                "Maze OpenGL — "
                "W/S: движение | "
                "A/D: поворот | "
                "ESC: выход"
            )


    pygame.quit()

    sys.exit()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
