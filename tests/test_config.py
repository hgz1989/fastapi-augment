"""
config 模块测试 — AugmentBaseSettings 配置管理
"""

from pydantic_settings import SettingsConfigDict

from fastapi_augment.config import (
    AugmentBaseSettings
)


# ── from_env() 类方法 ───────────────────────────────────────────────

class TestFromEnv:

    def test_from_env_with_env_file(self, tmp_path):
        """from_env 直接传入 .env 文件路径"""
        env_file = tmp_path / '.env'
        env_file.write_text('DATABASE_URL=sqlite:///test.db\n')

        class Settings(AugmentBaseSettings):
            database_url: str = ''

        s = Settings.from_env(env_file=str(env_file))
        assert s.database_url == 'sqlite:///test.db'

    def test_from_env_with_path_object(self, tmp_path):
        """from_env 支持 Path 对象"""
        env_file = tmp_path / '.env'
        env_file.write_text('NAME=hello\n')

        class Settings(AugmentBaseSettings):
            name: str = ''

        s = Settings.from_env(env_file=env_file)
        assert s.name == 'hello'

    def test_from_env_with_prefix(self, monkeypatch):
        """from_env 支持 env_prefix"""
        monkeypatch.setenv('APP_SECRET', 'my-secret')

        class Settings(AugmentBaseSettings):
            secret: str = ''

        s = Settings.from_env(env_prefix='APP_')
        assert s.secret == 'my-secret'

    def test_from_env_with_kwargs_override(self, monkeypatch):
        """from_env 的 kwargs 直接覆盖字段值"""
        monkeypatch.setenv('PORT', '8080')

        class Settings(AugmentBaseSettings):
            port: int = 0
            debug: bool = False

        s = Settings.from_env(port=9090, debug=True)
        assert s.port == 9090
        assert s.debug is True

    def test_from_env_without_overrides(self):
        """不传任何覆盖参数时，等同于直接实例化"""
        class Settings(AugmentBaseSettings):
            name: str = 'default'

        s = Settings.from_env()
        assert s.name == 'default'

    def test_from_env_with_nested_delimiter(self, monkeypatch):
        """from_env 支持 env_nested_delimiter"""
        monkeypatch.setenv('DB__HOST', 'localhost')
        monkeypatch.setenv('DB__PORT', '5432')

        from pydantic import BaseModel

        class DbConfig(BaseModel):
            host: str = ''
            port: int = 0

        class Settings(AugmentBaseSettings):
            db: DbConfig = DbConfig()

        s = Settings.from_env(env_nested_delimiter='__')
        assert s.db.host == 'localhost'
        assert s.db.port == 5432


# ── 基础加载 ─────────────────────────────────────────────────────────

class TestAugmentBaseSettingsBasic:

    def test_load_from_kwargs(self):
        """直接通过关键字参数传入配置"""
        class Settings(AugmentBaseSettings):
            database_url: str = ''
            debug: bool = False

        s = Settings(database_url='sqlite:///test.db', debug=True)
        assert s.database_url == 'sqlite:///test.db'
        assert s.debug is True

    def test_default_values(self):
        """未传入的字段使用默认值"""
        class Settings(AugmentBaseSettings):
            name: str = 'default'
            count: int = 0

        s = Settings()
        assert s.name == 'default'
        assert s.count == 0

    def test_env_var_override(self, monkeypatch):
        """环境变量覆盖默认值"""
        class Settings(AugmentBaseSettings):
            secret_key: str = 'fallback'

        monkeypatch.setenv('SECRET_KEY', 'from-env')
        s = Settings()
        assert s.secret_key == 'from-env'


# ── .env 文件加载 ────────────────────────────────────────────────────

class TestAugmentBaseSettingsDotEnv:

    def test_load_from_dotenv_via_model_config(self, tmp_path):
        """通过 model_config 指定 .env 文件加载"""
        env_file = tmp_path / '.env'
        env_file.write_text('DATABASE_URL=postgres://localhost/test\nDEBUG=true\n')

        class Settings(AugmentBaseSettings):
            model_config = SettingsConfigDict(env_file=str(env_file))
            database_url: str = ''
            debug: bool = False

        s = Settings()
        assert s.database_url == 'postgres://localhost/test'
        assert s.debug is True

    def test_env_var_priority_over_dotenv(self, tmp_path, monkeypatch):
        """环境变量优先级高于 .env 文件"""
        env_file = tmp_path / '.env'
        env_file.write_text('MY_VALUE=from-file\n')

        class Settings(AugmentBaseSettings):
            model_config = SettingsConfigDict(env_file=str(env_file))
            my_value: str = ''

        monkeypatch.setenv('MY_VALUE', 'from-env')
        s = Settings()
        assert s.my_value == 'from-env'

    def test_nonexistent_env_file_ignored(self, tmp_path):
        """不存在的 .env 文件不报错（pydantic-settings 默认行为）"""
        class Settings(AugmentBaseSettings):
            model_config = SettingsConfigDict(env_file=str(tmp_path / 'nonexistent.env'))
            name: str = 'default'

        s = Settings()
        assert s.name == 'default'


# ── 前缀 ─────────────────────────────────────────────────────────────

class TestAugmentBaseSettingsPrefix:

    def test_env_prefix_via_model_config(self, monkeypatch):
        """通过 model_config 设置 env_prefix"""
        monkeypatch.setenv('APP_DATABASE_URL', 'sqlite:///app.db')
        monkeypatch.setenv('OTHER_DATABASE_URL', 'sqlite:///other.db')

        class Settings(AugmentBaseSettings):
            model_config = SettingsConfigDict(env_prefix='APP_')
            database_url: str = ''

        s = Settings()
        assert s.database_url == 'sqlite:///app.db'


# ── 嵌套配置 ─────────────────────────────────────────────────────────

class TestAugmentBaseSettingsNested:

    def test_nested_delimiter_via_model_config(self, monkeypatch):
        """model_config 方式支持嵌套配置"""
        monkeypatch.setenv('DB__HOST', 'remote')
        monkeypatch.setenv('DB__PORT', '3306')

        from pydantic import BaseModel

        class DbConfig(BaseModel):
            host: str = ''
            port: int = 0

        class Settings(AugmentBaseSettings):
            model_config = SettingsConfigDict(env_nested_delimiter='__')
            db: DbConfig = DbConfig()

        s = Settings()
        assert s.db.host == 'remote'
        assert s.db.port == 3306


# ── extra='ignore' ───────────────────────────────────────────────────

class TestAugmentBaseSettingsExtra:

    def test_extra_env_vars_ignored(self, monkeypatch):
        """未在模型中声明的环境变量被忽略，不报错"""
        monkeypatch.setenv('UNKNOWN_VAR', 'whatever')

        class Settings(AugmentBaseSettings):
            name: str = 'test'

        s = Settings()
        assert s.name == 'test'

    def test_type_coercion(self, monkeypatch):
        """环境变量自动类型转换"""
        monkeypatch.setenv('PORT', '8080')
        monkeypatch.setenv('DEBUG', 'true')

        class Settings(AugmentBaseSettings):
            port: int = 0
            debug: bool = False

        s = Settings()
        assert s.port == 8080
        assert s.debug is True
