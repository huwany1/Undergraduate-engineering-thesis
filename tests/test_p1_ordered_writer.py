# -*- coding: utf-8 -*-
"""
P1 OrderedWriter 顺序与确定性测试
"""

import tempfile
from pathlib import Path
import pytest
import numpy as np

from p1_pipeline.ordered_writer import OrderedWriter, OrderedWriterError
from p1_pipeline.contracts import ReasonCode


@pytest.fixture
def temp_video_path():
    temp_dir = tempfile.mkdtemp()
    path = Path(temp_dir) / "output.mp4"
    yield path
    # cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_ordered_writer_sequential_success(temp_video_path):
    """顺序连续写入正常完成"""
    writer = OrderedWriter(temp_video_path, width=320, height=240, fps=25.0)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    for i in range(5):
        writer.write_frame(i, frame)

    assert writer.written_count == 5
    writer.close()
    assert temp_video_path.exists()


def test_ordered_writer_gap_violation(temp_video_path):
    """跳帧引发 INTERNAL_ORDER_VIOLATION 熔断"""
    writer = OrderedWriter(temp_video_path, width=320, height=240, fps=25.0)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    writer.write_frame(0, frame)
    with pytest.raises(OrderedWriterError) as exc_info:
        writer.write_frame(2, frame)  # 跳过 1

    assert exc_info.value.reason_code == ReasonCode.INTERNAL_ORDER_VIOLATION
    writer.close()


def test_ordered_writer_duplicate_violation(temp_video_path):
    """重复帧引发 INTERNAL_ORDER_VIOLATION 熔断"""
    writer = OrderedWriter(temp_video_path, width=320, height=240, fps=25.0)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)

    writer.write_frame(0, frame)
    with pytest.raises(OrderedWriterError) as exc_info:
        writer.write_frame(0, frame)  # 重复发送 0

    assert exc_info.value.reason_code == ReasonCode.INTERNAL_ORDER_VIOLATION
    writer.close()


def test_ordered_writer_dimension_mismatch(temp_video_path):
    """图像尺寸不匹配抛出 OUTPUT_WRITE_FAILED"""
    writer = OrderedWriter(temp_video_path, width=320, height=240, fps=25.0)
    wrong_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    with pytest.raises(OrderedWriterError) as exc_info:
        writer.write_frame(0, wrong_frame)

    assert exc_info.value.reason_code == ReasonCode.OUTPUT_WRITE_FAILED
    writer.close()
