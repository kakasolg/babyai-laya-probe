"""Small instruction-conditioned CNN policy for BabyAI GoToLocal (memoryless).
Input : image  int64 [N, 7, 7, 3]  MiniGrid egocentric partial view, image[i][j] = (object idx, colour idx, state)
        color  int64 [N]           mission colour  0 red 1 green 2 blue 3 purple 4 yellow 5 grey   (= MiniGrid COLOR_TO_IDX)
        kind   int64 [N]           mission type    0 ball 1 box 2 key
Output: logits float32 [N, 3]      0 turn left, 1 turn right, 2 forward   (= MiniGrid action numbers)"""
import torch, torch.nn as nn

class Policy(nn.Module):
    def __init__(self, ch=64, hid=256):
        super().__init__()
        self.ch, self.hid = ch, hid
        self.eo = nn.Embedding(11, 16); self.ec = nn.Embedding(6, 16)      # object idx, colour idx of each cell
        self.mc = nn.Embedding(6, 32); self.mt = nn.Embedding(3, 32)       # mission colour, mission type
        yy, xx = torch.meshgrid(torch.linspace(-1, 1, 7), torch.linspace(-1, 1, 7), indexing="ij")
        self.register_buffer("xy", torch.stack([xx, yy])[None])            # 2 coordinate channels
        self.c1 = nn.Conv2d(34, ch, 3, padding=1); self.c2 = nn.Conv2d(ch, ch, 3, padding=1); self.c3 = nn.Conv2d(ch, ch, 3, padding=1)
        self.f1 = nn.Linear(64, 2 * ch); self.f2 = nn.Linear(64, 2 * ch); self.f3 = nn.Linear(64, 2 * ch)   # FiLM: gamma, beta from the mission
        self.h1 = nn.Linear(ch * 49, hid); self.h2 = nn.Linear(hid, 3)

    @staticmethod
    def film(x, f, m):
        g, b = f(m).chunk(2, 1)
        return torch.relu(x * (1 + g[:, :, None, None]) + b[:, :, None, None])

    def forward(self, image, color, kind):
        x = torch.cat([self.eo(image[..., 0]), self.ec(image[..., 1])], -1).permute(0, 3, 1, 2)   # [N, 32, 7(i), 7(j)]
        x = torch.cat([x, self.xy.expand(x.shape[0], -1, -1, -1)], 1)                             # [N, 34, 7, 7]
        m = torch.cat([self.mc(color), self.mt(kind)], 1)                                         # [N, 64]
        x = self.film(self.c1(x), self.f1, m); x = self.film(self.c2(x), self.f2, m); x = self.film(self.c3(x), self.f3, m)
        return self.h2(torch.relu(self.h1(x.flatten(1))))
