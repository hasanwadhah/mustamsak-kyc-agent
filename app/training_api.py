"""HTTP routes of the AI training dashboard (app/training_center.py, static/training-ui.js)."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import learning, training_center as tc

router = APIRouter(prefix='/api/training')
Kind = Literal['digits', 'strips']


class Start(BaseModel):
    models: list[Literal['digits', 'numbers']] = Field(min_length=1, max_length=2)
    steps: int = Field(default=1500, ge=200, le=20000)
    share: float = Field(default=.3, ge=0, le=.8)


class Relabel(BaseModel):
    label: str = Field(min_length=1, max_length=7)


class Rollback(BaseModel):
    model: Literal['digits', 'numbers']


@router.get('')
def overview():
    return tc.overview()


@router.get('/progress')
def progress():
    return tc.progress()


@router.post('/start', status_code=202)
def start(body: Start):
    try:
        learning.start_training(models=body.models, steps=body.steps, share=body.share)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return tc.progress()


@router.post('/stop')
def stop():
    try:
        return learning.stop_training()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post('/evaluate')
def evaluate():
    if learning._training and learning._training.is_alive():
        raise HTTPException(409, 'انتظر انتهاء التدريب قبل التقييم.')
    return tc.evaluate()


@router.post('/rollback')
def rollback(body: Rollback):
    try:
        return tc.rollback(body.model)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))


@router.get('/samples/{kind}')
def samples(kind: Kind, label: str | None = None, offset: int = 0, limit: int = 60):
    return tc.list_samples(kind, label, max(0, offset), min(200, max(1, limit)))


@router.get('/samples/{kind}/image')
def sample_image(kind: Kind, id: str):
    try:
        return FileResponse(tc.sample_path(kind, id), media_type='image/png')
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, 'العينة غير موجودة.')


@router.patch('/samples/{kind}')
def relabel(kind: Kind, id: str, body: Relabel):
    try:
        return {'id': tc.relabel(kind, id, body.label)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, 'العينة غير موجودة.')


@router.delete('/samples/{kind}')
def delete(kind: Kind, id: str):
    try:
        tc.delete(kind, id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, 'العينة غير موجودة.')
    return {'ok': True}
