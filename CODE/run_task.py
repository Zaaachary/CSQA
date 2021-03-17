#! -*- encoding:utf-8 -*-
"""
@File    :   run_task.py
@Author  :   Zachary Li
@Contact :   li_zaaachary@163.com
@Dscpt   :   
"""
import argparse
import logging
import os
import time
from pprint import pprint

from tqdm import tqdm
from transformers import AlbertTokenizer, BertTokenizer

from csqa_task import data_processor
from csqa_task.controller import MultipleChoice
from model.AttnMerge import AlbertAddTFM, AlbertCSQA
from model.Baselines import AlbertBaseline
from model.HeadHunter import BertAttRanker
from utils.common import mkdir_if_notexist, result_dump, set_seed

logger = logging.getLogger("run_task")
console = logging.StreamHandler();console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)


def select_tokenizer(args):
    if "albert" in args.PTM_model_vocab_dir:
        return AlbertTokenizer.from_pretrained(args.PTM_model_vocab_dir)
    elif "bert" in args.PTM_model_vocab_dir:
        return BertTokenizer.from_pretrained(args.PTM_model_vocab_dir)
    else:
        logger.error("No Tokenizer Matched")

def select_task(args):
    '''
    task format: [data processor type]_[PTM model]_[model name]
    '''
    if args.task_name == "Origin_Albert_AttnMerge":
        return AlbertCSQA, data_processor.Baseline_Processor
    if args.task_name == "Origin_Albert_Baseline":
        return AlbertBaseline, data_processor.Baseline_Processor
    elif args.task_name == "Origin_Albert_AttnMergeAddTFM":
        return AlbertAddTFM, data_processor.Baseline_Processor
    elif args.task_name == "OMCS_Bert_AttRanker":
        return BertAttRanker, data_processor.OMCS_Processor
    elif args.task_name == "OMCS_Albert_Baseline":
        return AlbertBaseline, data_processor.OMCS_Processor

def set_result(args):
    '''
    set result dir name accroding to the task
    '''
    if args.mission == 'train':
        task_str = time.strftime(r'%b%d-%H%M') + f'_lr{args.lr:.0e}_warm{args.warmup_proportion:0.2}_decay{args.weight_decay:0.2}_seed{args.seed}'
        if 'OMCS' in args.task_name:
            task_str += f'_cs{args.cs_num}'

        args.result_dir = os.path.join(
            args.result_dir, args.task_name, 
            os.path.basename(args.PTM_model_vocab_dir), 
            task_str, ''
            )
    else:
        args.result_dir = args.saved_model_dir
    mkdir_if_notexist(args.result_dir)

    # set logging
    log_file_dir = os.path.join(args.result_dir, 'task_log.txt')
    logging.basicConfig(
        filename = log_file_dir,
        filemode = 'a',
        level = logging.INFO, 
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt = r"%y/%m/%d %H:%M"
        )

    result_dump(args, args.__dict__, 'task_args.json')
    pprint(args.__dict__)

def main(args):
    start = time.time()
    logger.info(f"start in {start}")
    set_result(args)
    set_seed(args)

    # load data and preprocess
    logger.info(f"select tokenizer and model for task {args.task_name}")
    tokenizer = select_tokenizer(args)
    model, Processor = select_task(args)

    if args.mission == 'train':
        processor = Processor(args, 'train')
        processor.load_data()
        train_dataloader = processor.make_dataloader(tokenizer, args.train_batch_size, False, 128, False)
        logger.info("train dataset loaded")

        processor = Processor(args, 'dev')
        processor.load_data()
        deval_dataloader = processor.make_dataloader(tokenizer, args.evltest_batch_size, False, 128, False)
        logger.info("dev dataset loaded")

    elif args.mission == 'eval':
        processor = Processor(args, 'dev')
        processor.load_data()
        deval_dataloader = processor.make_dataloader(tokenizer, args.evltest_batch_size, False, 128, False)
        logger.info("dev dataset loaded")

    elif args.mission == 'predict':
        processor = Processor(args, 'test')
        processor.load_data()
        deval_dataloader = processor.make_dataloader(tokenizer, args.evltest_batch_size, False, 128, False)
        logger.info("test dataset loaded")

    # initalize controller by model
    controller = MultipleChoice(args)
    controller.init(model)

    # run task accroading to mission
    if args.mission == 'train':
        controller.train(train_dataloader, deval_dataloader)

    elif args.mission == 'eval':
        controller.evaluate(deval_dataloader)

    elif args.mission == 'predict':
        pass

    end = time.time()
    logger.info("task total time:%.2f second"%(end-start))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # other param
    parser.add_argument('--task_name', type=str, default='AlbertAttnMerge')
    parser.add_argument('--mission', type=str, choices=['train', 'eval', 'predict'])
    parser.add_argument('--fp16', type=int, default=0)
    parser.add_argument('--gpu_ids', type=str, default='-1')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--save_mode', type=str, choices=['epoch', 'step', 'end'], default='end')
    parser.add_argument('--print_step', type=int, default=250)
    
    # hyper param
    parser.add_argument('--cs_num', type=int, default=0)
    parser.add_argument('--train_batch_size', type=int, default=4)
    parser.add_argument('--evltest_batch_size', type=int, default=4)
    parser.add_argument('--gradient_accumulation_steps', type=int, default=1)
    parser.add_argument('--num_train_epochs', type=int, default=5)
    parser.add_argument('--lr', type=float, default=2e-5)
    parser.add_argument('--warmup_proportion', type=float, default=0.1)
    parser.add_argument('--weight_decay', type=float, default=0.1)

    # data param
    parser.add_argument('--dataset_dir', type=str, default='../DATA')
    parser.add_argument('--result_dir', type=str, default=None)
    parser.add_argument('--saved_model_dir', type=str, default=None)     # 
    parser.add_argument('--PTM_model_vocab_dir', type=str, default=None)

    args_str = r"""
    --task_name OMCS_Albert_Baseline
    --mission train
    --fp16 0
    --gpu_ids -1
    --print_step 100

    --cs_num 2
    --train_batch_size 4
    --evltest_batch_size 16
    --gradient_accumulation_steps
    --num_train_epochs 4
    --lr 1e-5
    --warmup_proportion 0.1
    --weight_decay 0.1

    --dataset_dir ../DATA
    --pred_file_dir  ../DATA/result/task_result.json
    --model_save_dir ../DATA/result/TCmodel/
    --PTM_model_vocab_dir D:\CODE\Python\Transformers-Models\albert-base-v2
    """

    args = parser.parse_args()
    # args = parser.parse_args(args_str.split())

    main(args)
