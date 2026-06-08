"""
AudioUNet — модель для Audio Super-Resolution.
Восстанавливает высокие частоты на спектрограмме (частотная область).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

class AudioUNet(nn.Module):
    def __init__(self, n_fft=2048, hop_length=512):
        super().__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length

        def conv_block(in_ch, out_ch):
            return nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True)
            )

        self.enc1 = conv_block(2, 64)
        self.enc2 = conv_block(64, 128)
        self.enc3 = conv_block(128, 256)
        self.enc4 = conv_block(256, 512)
        self.pool = nn.MaxPool2d((2, 1))
        self.bottleneck = conv_block(512, 1024)

        def upconv_block(in_ch, out_ch):
            return nn.Sequential(
                nn.Upsample(scale_factor=(2, 1), mode='bilinear', align_corners=True),
                nn.Conv2d(in_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True)
            )

        self.dec4 = upconv_block(1024 + 512, 512)
        self.dec3 = upconv_block(512 + 256, 256)
        self.dec2 = upconv_block(256 + 128, 128)
        self.dec1 = upconv_block(128 + 64, 64)
        self.final = nn.Conv2d(64, 2, kernel_size=1)

    def _match_size(self, x, target):
        _, _, h, w = target.shape
        return F.interpolate(x, size=(h, w), mode='bilinear', align_corners=True)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        b = self.bottleneck(self.pool(e4))

        d4 = self.dec4(torch.cat([b, self._match_size(e4, b)], dim=1))
        d3 = self.dec3(torch.cat([self._match_size(d4, e3), e3], dim=1))
        d2 = self.dec2(torch.cat([self._match_size(d3, e2), e2], dim=1))
        d1 = self.dec1(torch.cat([self._match_size(d2, e1), e1], dim=1))

        out = self.final(d1)
        return x[:, :, :out.shape[2], :out.shape[3]] + out