import os
import torch
import cv2
import random
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import albumentations as A
from albumentations.pytorch import ToTensorV2
from option import get_option

opt = get_option()

train_transform = A.Compose(
    [
        A.RandomCrop(opt.image_size, opt.image_size),
        # A.D4(),
        # A.RandomGamma(),
        ToTensorV2(transpose_mask=True),
    ]
)

valid_transform = A.Compose(
    [
        A.PadIfNeeded(
            opt.valid_image_size, opt.valid_image_size, border_mode=cv2.BORDER_REFLECT
        ),
        A.CenterCrop(opt.valid_image_size, opt.valid_image_size),
        ToTensorV2(transpose_mask=True),
    ]
)


class Dataset(torch.utils.data.Dataset):
    def __init__(self, phase, opt, transform=None):
        self.phase = phase
        self.opt = opt
        self.dataset_root = opt.dataset_root
        self.transform = transform
        self.dataset_root = os.path.join(self.dataset_root, self.phase)
        self.image_list = os.listdir(os.path.join(self.dataset_root, "gt"))
        self.load_images_in_parallel()

    def load_image(self, path):
        image = cv2.imread(path)
        return image

    def load_images_in_parallel(self):
        # 定义一个内部函数来加载图像列表
        def load_images(image_paths, root_dir):
            with ThreadPoolExecutor(max_workers=24) as executor:
                images = list(
                    tqdm(
                        executor.map(
                            self.load_image,
                            [os.path.join(root_dir, img) for img in image_paths],
                        ),
                        total=len(image_paths),
                    )
                )
            return images

        self.input_list = load_images(
            self.image_list, os.path.join(self.dataset_root, "input")
        )
        self.target_list = load_images(
            self.image_list, os.path.join(self.dataset_root, "gt")
        )

    def __getitem__(self, index):
        low_image = self.input_list[index]
        high_image = self.target_list[index]
        if self.transform:
            transformed = self.transform(image=low_image, mask=high_image)
            low_image = transformed["image"]
            high_image = transformed["mask"]
        low_image = low_image / 127.5 - 1.0
        high_image = high_image / 127.5 - 1.0
        if random.random() < self.opt.ori_image_rate and self.phase == "train":
            return high_image.float(), high_image.float()
        else:
            return low_image.float(), high_image.float()

    def __len__(self):
        return len(self.image_list)


def get_dataloader(opt):
    train_dataset = Dataset(phase="train", opt=opt, transform=train_transform)
    valid_dataset = Dataset(phase="val", opt=opt, transform=valid_transform)
    train_dataloader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=opt.batch_size,
        shuffle=True,
        num_workers=opt.num_workers,
        pin_memory=True,
        drop_last=True,
    )
    valid_dataloader = torch.utils.data.DataLoader(
        valid_dataset,
        batch_size=1,
        shuffle=False,
        num_workers=opt.num_workers,
        pin_memory=True,
    )
    return train_dataloader, valid_dataloader


if __name__ == "__main__":
    train_dataloader, valid_dataloader = get_dataloader(opt)
    for i, (low, high) in enumerate(train_dataloader):
        pass
        print(low.shape, high.shape)
        if i == 0:
            break
    for i, (low, high) in enumerate(valid_dataloader):
        pass
        print(low.shape, high.shape)
        if i == 0:
            break
