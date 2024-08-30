from enum import StrEnum
from typing import Annotated, Any, Dict

import structlog
from pydantic import BaseModel, Field, ValidationError

from arachne.exceptions import UnsupportedActionType

LOG = structlog.get_logger()


class ActionType(StrEnum):
    CLICK = "click"
    INPUT_TEXT = "input_text"
    UPLOAD_FILE = "upload_file"

    SELECT_OPTION = "select_option"
    CHECKBOX = "checkbox"
    WAIT = "wait"
    NULL_ACTION = "null_action"
    SOLVE_CAPTCHA = "solve_captcha"
    TERMINATE = "terminate"
    COMPLETE = "complete"


class UserDefinedError(BaseModel):
    error_code: str
    reasoning: str
    confidence_float: float = Field(..., ge=0, le=1)


class SelectOption(BaseModel):
    label: str | None = None
    value: str | None = None
    index: int | None = None

    def __repr__(self) -> str:
        return f"SelectOption(label={self.label}, value={self.value}, index={self.index})"


class Action(BaseModel):
    action_type: ActionType
    confidence_float: float | None = None
    description: str | None = None
    reasoning: str | None = None
    element_id: Annotated[str, Field(coerce_numbers_to_str=True)] | None = None

    # DecisiveAction (CompleteAction, TerminateAction) fields
    errors: list[UserDefinedError] | None = None
    data_extraction_goal: str | None = None

    # WebAction fields
    file_name: str | None = None
    file_url: str | None = None
    download: bool | None = None
    is_upload_file_tag: bool | None = None
    text: str | None = None
    option: SelectOption | None = None
    is_checked: bool | None = None


class WebAction(Action):
    element_id: Annotated[str, Field(coerce_numbers_to_str=True)]


class DecisiveAction(Action):
    errors: list[UserDefinedError] = []


class ClickAction(WebAction):
    action_type: ActionType = ActionType.CLICK
    file_url: str | None = None
    download: bool = False

    def __repr__(self) -> str:
        return f"ClickAction(element_id={self.element_id}, file_url={self.file_url}, download={self.download})"


class InputTextAction(WebAction):
    action_type: ActionType = ActionType.INPUT_TEXT
    text: str

    def __repr__(self) -> str:
        return f"InputTextAction(element_id={self.element_id}, text={self.text})"


class UploadFileAction(WebAction):
    action_type: ActionType = ActionType.UPLOAD_FILE
    file_url: str
    is_upload_file_tag: bool = True

    def __repr__(self) -> str:
        return f"UploadFileAction(element_id={self.element_id}, file={self.file_url}, is_upload_file_tag={self.is_upload_file_tag})"




class NullAction(Action):
    action_type: ActionType = ActionType.NULL_ACTION


class SolveCaptchaAction(Action):
    action_type: ActionType = ActionType.SOLVE_CAPTCHA


class SelectOptionAction(WebAction):
    action_type: ActionType = ActionType.SELECT_OPTION
    option: SelectOption

    def __repr__(self) -> str:
        return f"SelectOptionAction(element_id={self.element_id}, option={self.option})"



class CheckboxAction(WebAction):
    action_type: ActionType = ActionType.CHECKBOX
    is_checked: bool

    def __repr__(self) -> str:
        return f"CheckboxAction(element_id={self.element_id}, is_checked={self.is_checked})"


class WaitAction(Action):
    action_type: ActionType = ActionType.WAIT


class TerminateAction(DecisiveAction):
    action_type: ActionType = ActionType.TERMINATE


class CompleteAction(DecisiveAction):
    action_type: ActionType = ActionType.COMPLETE
    data_extraction_goal: str | None = None


def parse_action(action: Dict[str, Any]) -> Action:
    if "id" in action:
        element_id = action["id"]
    elif "element_id" in action:
        element_id = action["element_id"]
    else:
        element_id = None

    reasoning = action["reasoning"] if "reasoning" in action else None
    confidence_float = action["confidence_float"] if "confidence_float" in action else None

    if "action_type" not in action or action["action_type"] is None:
        return NullAction(reasoning=reasoning, confidence_float=confidence_float)

    action_type = ActionType[action["action_type"].upper()]

    if action_type == ActionType.TERMINATE:
        return TerminateAction(
            reasoning=reasoning,
            confidence_float=confidence_float,
            errors=action["errors"] if "errors" in action else [],
        )

    if action_type == ActionType.CLICK:
        file_url = action["file_url"] if "file_url" in action else None
        return ClickAction(
            element_id=element_id,
            reasoning=reasoning,
            confidence_float=confidence_float,
            file_url=file_url,
            download=action.get("download", False),
        )

    if action_type == ActionType.INPUT_TEXT:
        return InputTextAction(
            element_id=element_id,
            text=action["text"],
            reasoning=reasoning,
            confidence_float=confidence_float,
        )

    if action_type == ActionType.UPLOAD_FILE:
        # TODO: see if the element is a file input element. if it's not, convert this action into a click action
        return UploadFileAction(
            element_id=element_id,
            confidence_float=confidence_float,
            file_url=action["file_url"],
            reasoning=reasoning,
        )

    if action_type == ActionType.SELECT_OPTION:
        option = action["option"]
        if option is None:
            raise ValueError("SelectOptionAction requires an 'option' field")
        label = option.get("label")
        value = option.get("value")
        index = option.get("index")
        if label is None and value is None and index is None:
            raise ValueError("At least one of 'label', 'value', or 'index' must be provided for a SelectOption")
        return SelectOptionAction(
            element_id=element_id,
            option=SelectOption(
                label=label,
                value=value,
                index=index,
            ),
            reasoning=reasoning,
            confidence_float=confidence_float,
        )

    if action_type == ActionType.CHECKBOX:
        return CheckboxAction(
            element_id=element_id,
            is_checked=action["is_checked"],
            reasoning=reasoning,
            confidence_float=confidence_float,
        )

    if action_type == ActionType.WAIT:
        return WaitAction(reasoning=reasoning, confidence_float=confidence_float)

    if action_type == "null":
        return NullAction(reasoning=reasoning, confidence_float=confidence_float)

    if action_type == ActionType.SOLVE_CAPTCHA:
        return SolveCaptchaAction(reasoning=reasoning, confidence_float=confidence_float)

    raise UnsupportedActionType(action_type=action_type)


def parse_actions( json_response: list[Dict[str, Any]]) -> list[Action]:
    actions: list[Action] = []
    for action in json_response:
        try:
            action_instance = parse_action(action=action)
            if isinstance(action_instance, TerminateAction):
                LOG.warning(
                    "Agent decided to terminate",
                    llm_response=json_response,
                    reasoning=action_instance.reasoning,
                    actions=actions,
                )
            actions.append(action_instance)

        except UnsupportedActionType:
            LOG.error(
                "Unsupported action type when parsing actions",
                raw_action=action,
                exc_info=True,
            )
        except (ValidationError, ValueError):
            LOG.warning(
                "Invalid action",
                raw_action=action,
                exc_info=True,
            )
        except Exception as e:
            LOG.error(
                "Failed to marshal action",
                e,
                raw_action=action,
                exc_info=True,
            )
    return actions


class ScrapeResult(BaseModel):
    """
    Scraped response from a webpage, including:
    1. JSON representation of what the user is seeing
    """

    scraped_data: dict[str, Any] | list[dict[str, Any]]
