import segmentation_models_pytorch as smp
import torch.nn as nn
import torch
import torch.nn.functional as F


class SKFusion(nn.Module):
    def __init__(self, dim, height=2, reduction=4):
        super(SKFusion, self).__init__()

        self.height = height
        d = max(int(dim / reduction), 8)

        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.mlp = nn.Sequential(
            nn.Conv2d(dim, d, 1, bias=False),
            nn.BatchNorm2d(d),
            nn.ReLU(),
            nn.Conv2d(d, dim * height, 1, bias=False),
        )

        self.softmax = nn.Softmax(dim=1)

    def forward(self, in_feats):
        B, C, H, W = in_feats[0].shape

        in_feats = torch.cat(in_feats, dim=1)
        in_feats = in_feats.view(B, self.height, C, H, W)

        feats_sum = torch.sum(in_feats, dim=1)
        attn = self.mlp(self.avg_pool(feats_sum))
        attn = self.softmax(attn.view(B, self.height, C, 1, 1))

        out = torch.sum(in_feats * attn, dim=1)
        return out


class SKFusionv2(nn.Module):
    def __init__(self, dim, height=2, reduction=4, kernel_size=3):
        super(SKFusionv2, self).__init__()

        self.height = height
        d = max(int(dim / reduction), 4)

        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.mlp = nn.Conv1d(1, self.height, kernel_size, 1, kernel_size // 2)

        self.softmax = nn.Softmax(dim=1)

    def forward(self, in_feats):
        B, C, H, W = in_feats[0].shape

        in_feats = torch.cat(in_feats, dim=1)
        in_feats = in_feats.view(B, self.height, C, H, W)

        feats_sum = torch.sum(in_feats, dim=1)
        attn = self.avg_pool(feats_sum)
        attn = attn.squeeze(-1).permute(0, 2, 1)
        attn = self.mlp(attn)
        attn = attn.permute(0, 2, 1)
        attn = self.softmax(attn.view(B, self.height, C, 1, 1))

        out = torch.sum(in_feats * attn, dim=1)
        return out


class PALayer(nn.Module):
    def __init__(self, channel):
        super(PALayer, self).__init__()
        self.pa = nn.Sequential(
            nn.Conv2d(channel, channel // 8, 1, padding=0, bias=True),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(channel // 8, 1, 1, padding=0, bias=True),
            nn.Sigmoid(),
        )

    def forward(self, x):
        y = self.pa(x)
        return x * y


class CALayer(nn.Module):
    def __init__(self, channel):
        super(CALayer, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.ca = nn.Sequential(
            nn.Conv2d(channel, channel // 8, 1, padding=0, bias=True),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(channel // 8, channel, 1, padding=0, bias=True),
            nn.Sigmoid(),
        )

    def forward(self, x):
        y = self.avg_pool(x)
        y = self.ca(y)
        return x * y


class CP_Attention_block(nn.Module):
    def __init__(self, dim, kernel_size):
        super(CP_Attention_block, self).__init__()
        self.conv1 = nn.Conv2d(dim, dim, kernel_size, 1, kernel_size // 2)
        self.act1 = nn.LeakyReLU(0.2, inplace=True)
        self.conv2 = nn.Conv2d(dim, dim, kernel_size, 1, kernel_size // 2)
        self.calayer = CALayer(dim)
        self.palayer = PALayer(dim)

    def forward(self, x):
        res = self.act1(self.conv1(x))
        res = res + x
        res = self.conv2(res)
        res = self.calayer(res)
        res = self.palayer(res)
        res += x
        return res


class mscheadv4(nn.Module):
    def __init__(self, in_channels):
        super(mscheadv4, self).__init__()
        self.in_channels = in_channels
        self.head1 = nn.Conv2d(in_channels, in_channels, 1, 1, 0)
        self.head2 = nn.Conv2d(in_channels, in_channels, 3, 1, 1)
        self.head3 = nn.Conv2d(in_channels, in_channels, 5, 1, 2)
        self.head4 = nn.Conv2d(in_channels, in_channels, 7, 1, 3)
        self.a = nn.Conv2d(in_channels * 5, 3, 7, 1, 3, padding_mode="reflect")
        self.b = nn.Conv2d(in_channels * 5, 3, 7, 1, 3, padding_mode="reflect")
        self.sk = SKFusion(in_channels, height=4)

    def forward(self, x):
        x1 = self.head1(x)
        x2 = self.head2(x)
        x3 = self.head3(x)
        x4 = self.head4(x)
        x = self.sk([x1, x2, x3, x4])
        x = torch.cat([x1, x2, x3, x4, x], dim=1)
        x1 = self.a(x)
        x2 = self.b(x)
        return x1, x2


class mscheadv5(nn.Module):
    def __init__(self, in_channels):
        super(mscheadv5, self).__init__()
        self.in_channels = in_channels
        self.head1 = nn.Conv2d(in_channels, in_channels, 1, 1, 0)
        self.head2 = nn.Conv2d(in_channels, in_channels, 3, 1, 1)
        self.head3 = nn.Conv2d(in_channels, in_channels, 5, 1, 2)
        self.head4 = nn.Conv2d(in_channels, in_channels, 7, 1, 3)
        self.sk = SKFusionv2(in_channels, height=4, kernel_size=7)
        self.b = nn.Sequential(
            nn.Conv2d(in_channels * 5, 3, 7, 1, 3, padding_mode="reflect"), nn.Tanh()
        )

    def forward(self, x):
        x1 = self.head1(x)
        x2 = self.head2(x)
        x3 = self.head3(x)
        x4 = self.head4(x)
        x = self.sk([x1, x2, x3, x4])
        x = torch.cat([x1, x2, x3, x4, x], dim=1)
        x = self.b(x)
        return x


if __name__ == "__main__":
    model = mscheadv5(32)
    x = torch.randn(2, 32, 512, 512)

    y = model(x)
    for i in y:
        print(i.shape)
