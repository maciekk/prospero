import json
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from prospero.models.planner import PlannerConfig
from prospero.models.portfolio import Portfolio

DATA_DIR = Path.home() / ".prospero"


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# --- Planner config (TOML) ---

def _planner_path() -> Path:
    return DATA_DIR / "planner.toml"


def load_planner_config() -> PlannerConfig | None:
    path = _planner_path()
    if not path.exists():
        return None
    text = path.read_text()
    data = tomllib.loads(text)
    return PlannerConfig.model_validate(data)


def save_planner_config(config: PlannerConfig) -> Path:
    _ensure_dir()
    path = _planner_path()
    # Write TOML manually (stdlib has reader but no writer)
    lines: list[str] = []
    for key, value in config.model_dump(mode='json').items():
        if value is None:
            continue  # omit None values; Pydantic will use defaults on load
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key} = []")
            else:
                items = []
                for item in value:
                    pairs = [
                        f"{k} = {v}" if isinstance(v, (int, float)) else f'{k} = "{v}"'
                        for k, v in item.items()
                    ]
                    items.append("{" + ", ".join(pairs) + "}")
                lines.append(f"{key} = [{', '.join(items)}]")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f'{key} = "{value}"')
    path.write_text("\n".join(lines) + "\n")
    return path


# --- Portfolio (JSON) ---

def _portfolio_path() -> Path:
    return DATA_DIR / "portfolio.json"


def load_portfolio() -> Portfolio:
    path = _portfolio_path()
    if not path.exists():
        return Portfolio()
    text = path.read_text()
    return Portfolio.model_validate_json(text)


def save_portfolio(portfolio: Portfolio) -> Path:
    _ensure_dir()
    path = _portfolio_path()
    path.write_text(portfolio.model_dump_json(indent=2) + "\n")
    return path
