"""Lightweight 1D ResNet for the five PTB-XL diagnostic superclasses."""

from __future__ import annotations

import torch
from torch import nn


class ResidualBlock(nn.Module):
    """Two-convolution residual block with optional downsampling."""

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        super().__init__()
        self.conv1 = nn.Conv1d(
            in_channels, out_channels, kernel_size=7, stride=stride, padding=3,
            bias=False,
        )
        self.norm1 = nn.BatchNorm1d(out_channels)
        self.conv2 = nn.Conv1d(
            out_channels, out_channels, kernel_size=7, padding=3, bias=False,
        )
        self.norm2 = nn.BatchNorm1d(out_channels)
        self.activation = nn.ReLU(inplace=True)
        if stride != 1 or in_channels != out_channels:
            self.skip = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, kernel_size=1, stride=stride,
                          bias=False),
                nn.BatchNorm1d(out_channels),
            )
        else:
            self.skip = nn.Identity()

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        residual = self.skip(values)
        values = self.activation(self.norm1(self.conv1(values)))
        values = self.norm2(self.conv2(values))
        return self.activation(values + residual)


class ECGResNet1D(nn.Module):
    """Multi-label ECG network accepting [batch, 12 leads, 1000 samples]."""

    def __init__(self, class_count: int = 5):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(12, 24, kernel_size=15, stride=2, padding=7, bias=False),
            nn.BatchNorm1d(24),
            nn.ReLU(inplace=True),
        )
        self.stage1 = nn.Sequential(
            ResidualBlock(24, 24), ResidualBlock(24, 24),
        )
        self.stage2 = nn.Sequential(
            ResidualBlock(24, 48, stride=2), ResidualBlock(48, 48),
        )
        self.stage3 = nn.Sequential(
            ResidualBlock(48, 96, stride=2), ResidualBlock(96, 96),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Linear(96, class_count)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        if values.ndim != 3 or values.shape[1:] != (12, 1000):
            raise ValueError("ECGResNet1D expects input shape [batch, 12, 1000].")
        values = self.stem(values)
        values = self.stage1(values)
        values = self.stage2(values)
        values = self.stage3(values)
        return self.classifier(self.pool(values).squeeze(-1))


def parameter_count(model: nn.Module) -> int:
    """Count trainable parameters for model-card reporting."""
    return sum(parameter.numel() for parameter in model.parameters()
               if parameter.requires_grad)
