import gym
import argparse
import torch
#from gym.envs.mujoco import HalfCheetahEnv

import rlkit.torch.pytorch_util as ptu
from rlkit.torch.sac.diayn.diayn_env_replay_buffer import DIAYNEnvReplayBuffer
from rlkit.envs.wrappers import NormalizedBoxEnv
from rlkit.launchers.launcher_util import setup_logger
from rlkit.torch.sac.diayn.diayn_path_collector import DIAYNMdpPathCollector
from rlkit.samplers.data_collector.step_collector import MdpStepCollector
from rlkit.torch.sac.diayn.policies import SkillTanhGaussianPolicy, MakeDeterministic
from rlkit.torch.sac.diayn.diayn import DIAYNTrainer
from rlkit.torch.networks import FlattenMlp
from rlkit.torch.sac.diayn.diayn_torch_online_rl_algorithm import DIAYNTorchOnlineRLAlgorithm


def get_algorithm(expl_env, eval_env, skill_dim, epochs, file=None):
    obs_dim = expl_env.observation_space.low.size
    action_dim = eval_env.action_space.low.size
    skill_dim = skill_dim
    M = variant['layer_size']

    if file:
        print("old policy")
        data = torch.load(file)
        policy = data['evaluation/policy']
        qf1 = data['trainer/qf1']
        qf2 = data['trainer/qf2']
        target_qf1 = data['trainer/target_qf1']
        target_qf2 = data['trainer/target_qf2']
        df = data['trainer/df']
        policy = data['trainer/policy']
        eval_policy = MakeDeterministic(policy)

    else:
        print("new policy")
        qf1 = FlattenMlp(
            input_size=obs_dim + action_dim + skill_dim,
            output_size=1,
            hidden_sizes=[M, M],
        )
        qf2 = FlattenMlp(
            input_size=obs_dim + action_dim + skill_dim,
            output_size=1,
            hidden_sizes=[M, M],
        )
        target_qf1 = FlattenMlp(
            input_size=obs_dim + action_dim + skill_dim,
            output_size=1,
            hidden_sizes=[M, M],
        )
        target_qf2 = FlattenMlp(
            input_size=obs_dim + action_dim + skill_dim,
            output_size=1,
            hidden_sizes=[M, M],
        )
        df = FlattenMlp(
            input_size=obs_dim,
            output_size=skill_dim,
            hidden_sizes=[M, M],
        )
        policy = SkillTanhGaussianPolicy(
            obs_dim=obs_dim + skill_dim,
            action_dim=action_dim,
            hidden_sizes=[M, M],
            skill_dim=skill_dim
        )
        eval_policy = MakeDeterministic(policy)

    eval_path_collector = DIAYNMdpPathCollector(
        eval_env,
        eval_policy,
    )
    expl_step_collector = MdpStepCollector(
        expl_env,
        policy,
    )
    replay_buffer = DIAYNEnvReplayBuffer(
        variant['replay_buffer_size'],
        expl_env,
        skill_dim,
    )
    trainer = DIAYNTrainer(
        env=eval_env,
        policy=policy,
        qf1=qf1,
        qf2=qf2,
        df=df,
        target_qf1=target_qf1,
        target_qf2=target_qf2,
        **variant['trainer_kwargs']
    )
    variant['algorithm_kwargs']['num_epochs'] = epochs
    algorithm = DIAYNTorchOnlineRLAlgorithm(
        trainer=trainer,
        exploration_env=expl_env,
        evaluation_env=eval_env,
        exploration_data_collector=expl_step_collector,
        evaluation_data_collector=eval_path_collector,
        replay_buffer=replay_buffer,
        **variant['algorithm_kwargs']
    )
    log_dir = setup_logger('DIAYN_' + str(skill_dim) + '_' + expl_env.wrapped_env.spec.id, 
                 variant=variant)
    algorithm.log_dir = log_dir
    return algorithm


def experiment(algorithm, expl_env, eval_env, args):
    algorithm.to(ptu.device)
    algorithm.train()


# noinspection PyTypeChecker
variant = dict(
    algorithm="DIAYN",
    version="normal",
    layer_size=256,
    replay_buffer_size=int(1E6),
    algorithm_kwargs=dict(
        num_epochs=1000,
        num_eval_steps_per_epoch=5000,
        num_trains_per_train_loop=1000,
        num_expl_steps_per_train_loop=1000,
        min_num_steps_before_training=1000,
        max_path_length=1000,
        batch_size=256,
    ),
    trainer_kwargs=dict(
        discount=0.99,
        soft_target_tau=5e-3,
        target_update_period=1,
        policy_lr=3E-4,
        qf_lr=3E-4,
        reward_scale=1,
        use_automatic_entropy_tuning=True,
    ),
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('env', type=str,
                        help='environment')
    parser.add_argument('--skill_dim', type=int, default=10,
                        help='skill dimension')
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument("--file", type=str, default=None)
    args = parser.parse_args()
    expl_env = NormalizedBoxEnv(gym.make(str(args.env)))
    eval_env = NormalizedBoxEnv(gym.make(str(args.env)))
    # expl_env = NormalizedBoxEnv(HalfCheetahEnv())
    # eval_env = NormalizedBoxEnv(HalfCheetahEnv())

    algorithm = get_algorithm(expl_env,
                              eval_env,
                              args.skill_dim,
                              args.epochs,
                              file=args.file)
    # ptu.set_gpu_mode(True)  # optionally set the GPU (default=False)
    experiment(algorithm, expl_env, eval_env, args)
