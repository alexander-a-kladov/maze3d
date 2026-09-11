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

MAX_FLOORS = 2

WALL_TEXTURE_FILE = BASE_DIR / "textures" / "w.png"
FLOOR_TEXTURE_FILE = BASE_DIR / "textures" / "f.png"
FINISH_TEXTURE_FILE = BASE_DIR / "textures" / "e.png"

WALK_SOUND_FILE = BASE_DIR / "sounds" / "walk.wav"


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

MOVE_SPEED = 3.5
TURN_SPEED = 125.0

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

                    # k НЕ является клеткой лабиринта.
                    # Под ним появляется обычный пол.
                    clean_grid[z][x] = "f"

                    objects.append({
                        "type": "k",
                        "x": x,
                        "z": z
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
        walk_sound
        ):

        self.floors = floors
        self.floor_count = len(floors)

        self.wall_texture = wall_texture
        self.floor_texture = floor_texture
        self.finish_texture = finish_texture

        self.objects = {}

        self.load_objects()

        self.walk_sound = walk_sound
        self.walk_channel = None

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
            )
        }

        for symbol, (
            obj_file,
            mtl_file
        ) in object_files.items():

            if not obj_file.exists():

                print(
                    f"Предупреждение: "
                    f"не найден объект {obj_file}"
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

        # Высота объекта = половина высоты стены.
        # Стена имеет высоту 2.0.
        target_height = CELL_SIZE * 0.5

        scale = target_height / object_height

        # Центр клетки.
        center_x = x + CELL_SIZE / 2
        center_z = z + CELL_SIZE / 2

        # Ставим нижнюю точку объекта на верхнюю
        # поверхность пола.
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

    # ========================================================
    # КООРДИНАТЫ
    # ========================================================
    
    def floor_y(self):
        return (
            self.current_floor
            * FLOOR_LEVEL_HEIGHT
        )

    def change_floor(self, direction):

        current_x = math.floor(
            self.x / CELL_SIZE
        )

        current_z = math.floor(
            self.z / CELL_SIZE
        )

        # ========================================================
        # ВВЕРХ
        # ========================================================

        if direction > 0:

            target_floor = (
                self.current_floor + 1
            )

            # Выше этажей нет
            if target_floor >= self.floor_count:
                return

            target_grid = self.floors[
                target_floor
            ]["grid"]

            # Проверяем координату Z
            if (
                current_z < 0
                or current_z >= len(target_grid)
            ):
                return

            row = target_grid[current_z]

            # Проверяем координату X
            if (
                current_x < 0
                or current_x >= len(row)
            ):
                return

            # Сверху обязательно должна быть пустая клетка
            if row[current_x] != " ":
                return

            # Переходим вверх
            self.current_floor = target_floor

        # ========================================================
        # ВНИЗ
        # ========================================================

        else:

            # Вниз можно только если текущая клетка пустая
            if self.cell_at_world(
                self.x,
                self.z
            ) != " ":
                return

            target_floor = (
                self.current_floor - 1
            )

            # Ниже этажей нет
            if target_floor < 0:
                return

            # Переходим вниз
            self.current_floor = target_floor

        # ========================================================
        # Обновляем текущую карту
        # ========================================================

        self.grid = self.floors[
            self.current_floor
        ]["grid"]

        self.width = self.floors[
            self.current_floor
        ]["width"]

        self.height = self.floors[
            self.current_floor
        ]["height"]

    def cell_at_world(self, x, z):

        cx = math.floor(x / CELL_SIZE)
        cz = math.floor(z / CELL_SIZE)

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


    # ========================================================
    # СТОЛКНОВЕНИЯ
    # ========================================================

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

            cell = self.cell_at_world(
                px,
                pz
            )

            if cell == "w" or cell == "e":
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

                    world_x = (
                        x * CELL_SIZE
                    )

                    world_z = (
                        z * CELL_SIZE
                    )

                    if not self.is_visible_from_player(
                        world_x + CELL_SIZE / 2,
                        world_z + CELL_SIZE / 2
                    ):
                        continue
                    countm += 1
                    if ch == "f" or ch == "s":

                        self.draw_floor_cube(
                            world_x,
                            world_z
                        )

                    elif ch == "w":

                        self.draw_wall_cube(
                            world_x,
                            world_z
                        )

                    elif ch == "e":

                        self.draw_finish_cube(
                            world_x,
                            world_z
                        )

            # ================================================
            # ОБЪЕКТЫ
            # ================================================

            for obj in floor["objects"]:

                if obj["type"] == "k":

                    world_x = (
                        obj["x"] * CELL_SIZE
                    )

                    world_z = (
                        obj["z"] * CELL_SIZE
                    )

                    if not self.is_visible_from_player(
                        world_x + CELL_SIZE / 2,
                        world_z + CELL_SIZE / 2
                    ):
                        continue
                    counto += 1
                    self.draw_object(
                        "k",
                        world_x,
                        world_z
                    )

        self.current_floor = saved_floor
        #print(countm, counto)

        self.draw_sky_ceiling()


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


    setup_opengl(
        width,
        height
    )


    game = MazeGame(

        floors,

        wall_texture,
        floor_texture,
        finish_texture,

        walk_sound
    )


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

        pygame.display.flip()


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
