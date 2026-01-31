"""Input prompts and validators for CLI."""

from typing import Any, List, Optional, Callable
import questionary
from questionary import Validator, ValidationError


class NumberValidator(Validator):
    """Validator for numeric input."""
    
    def __init__(self, min_val: Optional[float] = None, 
                 max_val: Optional[float] = None,
                 allow_float: bool = True):
        self.min_val = min_val
        self.max_val = max_val
        self.allow_float = allow_float
    
    def validate(self, document) -> None:
        text = document.text
        
        try:
            if self.allow_float:
                value = float(text)
            else:
                value = int(text)
        except ValueError:
            raise ValidationError(
                message="Please enter a valid number",
                cursor_position=len(text)
            )
        
        if self.min_val is not None and value < self.min_val:
            raise ValidationError(
                message=f"Value must be at least {self.min_val}",
                cursor_position=len(text)
            )
        
        if self.max_val is not None and value > self.max_val:
            raise ValidationError(
                message=f"Value must be at most {self.max_val}",
                cursor_position=len(text)
            )


class SymbolValidator(Validator):
    """Validator for trading pair symbols."""
    
    def validate(self, document) -> None:
        text = document.text.strip()
        
        if not text:
            raise ValidationError(
                message="Symbol cannot be empty",
                cursor_position=0
            )
        
        if "/" not in text:
            raise ValidationError(
                message="Symbol must be in format BASE/QUOTE (e.g., BTC/USDT)",
                cursor_position=len(text)
            )


def prompt_number(message: str, default: float = 0, 
                  min_val: Optional[float] = None,
                  max_val: Optional[float] = None,
                  allow_float: bool = True) -> float:
    """
    Prompt for a numeric value with validation.
    
    Args:
        message: Prompt message
        default: Default value
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        allow_float: Allow decimal values
        
    Returns:
        User-entered number
    """
    validator = NumberValidator(min_val, max_val, allow_float)
    
    result = questionary.text(
        message,
        default=str(default),
        validate=validator
    ).ask()
    
    return float(result) if allow_float else int(result)


def prompt_symbol(message: str = "Enter trading pair:", 
                  default: str = "BTC/USDT") -> str:
    """
    Prompt for a trading symbol with validation.
    
    Args:
        message: Prompt message
        default: Default symbol
        
    Returns:
        User-entered symbol
    """
    return questionary.text(
        message,
        default=default,
        validate=SymbolValidator()
    ).ask()


def prompt_select(message: str, choices: List[Any], 
                  default: Optional[Any] = None) -> Any:
    """
    Prompt for a selection from a list.
    
    Args:
        message: Prompt message
        choices: List of choices (can be strings or dicts with name/value)
        default: Default selection
        
    Returns:
        Selected value
    """
    return questionary.select(
        message,
        choices=choices,
        default=default
    ).ask()


def prompt_confirm(message: str, default: bool = True) -> bool:
    """
    Prompt for confirmation.
    
    Args:
        message: Prompt message
        default: Default answer
        
    Returns:
        User confirmation
    """
    return questionary.confirm(message, default=default).ask()


def prompt_text(message: str, default: str = "", 
                password: bool = False) -> str:
    """
    Prompt for text input.
    
    Args:
        message: Prompt message
        default: Default value
        password: Hide input (for passwords/secrets)
        
    Returns:
        User-entered text
    """
    if password:
        return questionary.password(message).ask()
    return questionary.text(message, default=default).ask()


def prompt_checkbox(message: str, choices: List[Any]) -> List[Any]:
    """
    Prompt for multiple selections.
    
    Args:
        message: Prompt message
        choices: List of choices
        
    Returns:
        List of selected values
    """
    return questionary.checkbox(message, choices=choices).ask()


def prompt_date_range(default_days: int = 365) -> tuple:
    """
    Prompt for a date range.
    
    Args:
        default_days: Default number of days to look back
        
    Returns:
        Tuple of (start_date, end_date) as datetime objects
    """
    from datetime import datetime, timedelta
    
    choices = [
        {"name": "Last 30 days", "value": 30},
        {"name": "Last 90 days", "value": 90},
        {"name": "Last 180 days", "value": 180},
        {"name": "Last 365 days", "value": 365},
        {"name": "Last 2 years", "value": 730},
        {"name": "Custom", "value": "custom"}
    ]
    
    selection = prompt_select("Select time period:", choices)
    
    end_date = datetime.now()
    
    if selection == "custom":
        days = int(prompt_number("Enter number of days:", default=default_days, min_val=1))
    else:
        days = selection
    
    start_date = end_date - timedelta(days=days)
    
    return start_date, end_date
