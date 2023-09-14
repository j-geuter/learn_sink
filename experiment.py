"""
experiment.py
-------------

Script for creating, training and testing a puma and a deer and saving the
results.

Let the hunt begin!
"""

# Imports
import datetime
import os
import torch
import ot
from tqdm import tqdm
from geometry import get_cost
from sinkhorn import sink_vec
from train import the_hunt
from nets import GenNet, PredNet
from loss import hilb_proj_loss
from data_funcs import preprocessor, test_set_sampler

# Create 'stamp' folder for saving results
current_time = datetime.datetime.now()
formatted_time = current_time.strftime('%m-%d_%H_%M_%S')
stamp_folder_path = './stamps/stamp_main_'+formatted_time
os.mkdir(stamp_folder_path)

# Problem hyperparameters
length_prior = 7
length = 28
dim_prior = length_prior**2
dim = length**2
dust_const = 1e-6
skip_const = 0.75
width_gen = 6 * dim
width_pred = 6 * dim

# Training Hyperparams
n_loops = 50000
n_mini_loops_gen = 1
n_mini_loops_pred = 1
n_batch = 200
n_accumulation_gen = 5
n_accumulation_pred = 5
lr_gen = 0.25
lr_pred = 0.25
lr_fact_gen = 1.0
lr_fact_pred = 0.99997
learn_gen = True
bootstrapped = True
n_boot = 40
extend_data = False
test_iter = 1000
n_test = 100
checkpoint = n_loops

# Device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'Device: {device}')

# Initialization of cost matrix
cost = get_cost(length).double().to(device)

# Regularization parameter
eps = cost.max() * 5e-4
print(f'Entropic regularization param: {eps}')

# Loading, preprocessing, and sampling for the test sets dictionary
mnist = torch.load('./data/mnist.pt')
cifar = torch.load('./data/cifar.pt')
lfw = torch.load('./data/lfw.pt')
bear = torch.load('./data/bear.pt')
quickdraw = torch.load('./data/quickdraw.pt')

mnist = preprocessor(mnist, length, dust_const)
cifar = preprocessor(cifar, length, dust_const)
lfw = preprocessor(lfw, length, dust_const)
bear = preprocessor(bear, length, dust_const)
quickdraw = preprocessor(quickdraw, length, dust_const)

mnist = test_set_sampler(mnist, n_test).double().to(device)
cifar = test_set_sampler(cifar, n_test).double().to(device)
lfw = test_set_sampler(lfw, n_test).double().to(device)
bear = test_set_sampler(bear, n_test).double().to(device)
quickdraw = test_set_sampler(quickdraw, n_test).double().to(device)

test_sets = {'mnist': mnist,'cifar': cifar, 'lfw': lfw, 'bear': bear,
             'quickdraw': quickdraw}

# Creating a dictionary of test emds, and test targets for each test set
test_sinks = {}
test_emds = {}
test_T = {}

print('Computing test emds, sinks, and targets...')
for key in test_sets.keys():
    print(f'{key}:')
    with torch.no_grad():

        X = test_sets[key]

        V0 = torch.ones_like(X[:, :dim])
        V = sink_vec(X[:, :dim], X[:, dim:], cost, eps, V0, 2000)[1]
        V = torch.log(V)
        T = V - torch.unsqueeze(V.mean(dim=1), 1).repeat(1, dim)
        test_T[key] = T

        sinks = []
        for x in tqdm(X):
            mu = x[:dim] / x[:dim].sum()
            nu = x[dim:] / x[dim:].sum()
            sink = ot.sinkhorn2(mu, nu, cost, eps)
            sinks.append(sink)
        sinks = torch.tensor(sinks)
        test_sinks[key] = sinks

        emds = []
        for x in tqdm(X):
            mu = x[:dim] / x[:dim].sum()
            nu = x[dim:] / x[dim:].sum()
            emd = ot.emd2(mu, nu, cost)
            emd.append(emd)
        emd = torch.tensor(emd)
        test_sinks[key] = emd

# Initialization of loss function
loss_func = hilb_proj_loss

# Initialization of nets
deer = GenNet(dim_prior, dim, width_gen, dust_const,
              skip_const).double().to(device)
puma = PredNet(dim, width_pred).double().to(device)

# no. layers in each net
n_layers_gen = len(deer.layers)
n_layers_pred = len(puma.layers)

# Load model state dict
#deer.load_state_dict(torch.load(f'{stamp_folder_path}/deer.pt'))
#puma.load_state_dict(torch.load(f'{stamp_folder_path}/puma.pt'))

# Training mode
deer.train()
puma.train()

# Get total number of trainable parameters
n_params_gen = sum(p.numel() for p in deer.parameters() if p.requires_grad)
n_params_pred = sum(p.numel() for p in puma.parameters() if p.requires_grad)
print(f'No. trainable parameters in gen net: {n_params_gen}')
print(f'No. trainable parameters in pred net: {n_params_pred}')

# Create txt file in stamp for hyperparams
current_date = datetime.datetime.now().strftime('%d.%m.%Y')
hyperparams = {
    'date': current_date,
    'prior distribution length': length_prior,
    'data length': length,
    'prior distribution dimension': dim_prior,
    'data dimension': dim,
    'regularization parameter': eps,
    'dust constant': dust_const,
    'skip connection constant': skip_const,
    'no. layers gen': n_layers_gen,
    'no. layers pred': n_layers_pred,
    'hidden layer width gen': width_gen,
    'hidden layer width pred': width_pred,
    'total no. trainable parameters gen': n_params_gen,
    'total no. trainable parameters pred': n_params_pred,
    'device': device,
    'gen net learning rate': lr_gen,
    'pred net learning rate': lr_pred,
    'learning rate scale factor gen': lr_fact_gen,
    'learning rate scale factor pred': lr_fact_pred,
    'no. unique data points gen': n_loops*n_mini_loops_gen*n_batch,
    'no. unique data points pred': n_loops*n_mini_loops_pred*n_batch,
    'no. loops' : n_loops,
    'no. mini loops gen' : n_mini_loops_gen,
    'no. mini loops pred' : n_mini_loops_pred,
    'batch size gradient update' : n_batch,
    'batch size per step gen' : n_batch * n_accumulation_gen,
    'batch size per step pred' : n_batch * n_accumulation_pred,
    'no. gradients per step gen' : n_accumulation_gen,
    'no. gradients per step pred' : n_accumulation_pred,
    'test_iter': test_iter,
    'no. test samples': n_test,
    'learn gen?': learn_gen,
    'bootstrapped?': bootstrapped,
    'no. bootstraps': n_boot,
    'extend data?': extend_data,
    'checkpoint': checkpoint,
}

# Print hyperparams
for key, value in hyperparams.items():
    print(f'{key}: {value}')

# Define the output file path
output_file = f'{stamp_folder_path}/params.txt'

# Save the hyperparams to the text file
with open(output_file, 'w', encoding='utf-8') as file:
    for key, value in hyperparams.items():
        file.write(f'{key}: {value}\n')

# Run the hunt
(train_losses,
test_losses,
test_rel_errs_sink,
test_rel_errs_emd,
test_mcvs,
warmstarts_emd,
warmstarts_mcv) = the_hunt(
        deer,
        puma,
        loss_func,
        cost,
        eps,
        dust_const,
        dim_prior,
        dim,
        device,
        test_sets,
        test_sinks,
        test_emds,
        test_T,
        n_loops,
        n_mini_loops_gen,
        n_mini_loops_pred,
        n_batch,
        n_accumulation_gen,
        n_accumulation_pred,
        lr_pred,
        lr_gen,
        lr_fact_gen,
        lr_fact_pred,
        learn_gen,
        bootstrapped,
        n_boot,
        extend_data,
        test_iter,
        stamp_folder_path,
        checkpoint,
        )

print('The hunt is over. Time to rest.')
