import torch
import matplotlib.pyplot as plt
import seaborn as sns
import torch.nn.functional as F
from captum.attr import IntegratedGradients
import matplotlib.pyplot as plt
from captum.attr import IntegratedGradients, Saliency
from captum.attr import LayerGradCam
from captum.attr import Saliency, DeepLift, ShapleyValueSampling,GradientShap, LayerIntegratedGradients
import os
import pickle

def pseudo_label(model, test_loader, criterion, device, save_dir, model_name, patient, treshold_labels, method):

    pseudo_labels = []
    
    if method == 'ig':
        pseudo_labels.append(gradient_integrated(test_loader, criterion, model_name, model, patient, device, treshold_labels))
    
    elif method == 'vg':
        pseudo_labels.append(vanilla_gradients(test_loader, criterion, model_name, model, patient, device, treshold_labels))
    
    # elif method == 'grad_cam':
    #     pseudo_labels.append(grad_cam(test_loader, criterion, model_name, model, patient, device, treshold_labels))
            
    save_pseudo_labels(pseudo_labels, save_dir, model_name, patient, method)
    return pseudo_labels


def gradient_integrated(test_loader, criterion, model_name, model, patient, device, treshold_labels):

    model.eval()
    if model_name == 'LSTM':
        model.train()
    
    for batch_idx, (inputs, targets, lengths, inputs2) in enumerate(test_loader):
        
        inputs, targets = inputs.to(device, non_blocking=True).float(), targets.to(device, non_blocking=True).float()
        lengths = lengths.to('cpu')
        
        inputs.requires_grad = True
        
        if model_name == 'moment':
            ig_gradients = integrated_gradients(inputs, model, lengths, 0, baseline=None, steps=5)
        else: 
            ig = IntegratedGradients(model)
            ig_gradients = ig.attribute(inputs, baselines=inputs * 0, target=0, additional_forward_args=lengths)
        
        slc = torch.relu(ig_gradients)
        
        if model_name != 'LSTM':
            slc = smooth_gradients(slc, kernel_size=8)
        saliency = torch.nn.functional.interpolate(slc.unsqueeze(0), size=(slc.shape[1], 33), mode='nearest').squeeze(0)
        
        map = torch.zeros_like(saliency)
        
        for i in range(saliency.shape[0]):
            map[i] = (saliency[i] - saliency[i].min()) / (saliency[i].max() - saliency[i].min())
        
        # still need to revise this for several batches
        binary_map = (map[0][0:lengths[0]].sum(dim=1) < treshold_labels).int().detach().cpu().numpy()
        
        torch.cuda.empty_cache()
        
    return binary_map


def integrated_gradients(inputs, model, lengths, target_label_idx, baseline=None, steps=5):
    
    if baseline is None:
        baseline = torch.zeros_like(inputs).to(inputs.device)
    
    integrated_grads = torch.zeros_like(inputs).to(inputs.device)
    
    for i in range(steps + 1):
        alpha = float(i) / steps
        scaled_input = baseline + alpha * (inputs - baseline)
        scaled_input = scaled_input.requires_grad_(True)

        outputs = model(scaled_input)

        loss = outputs[:, target_label_idx].sum()
        
        grads = torch.autograd.grad(loss, scaled_input, create_graph=False)[0]
        integrated_grads += grads * (inputs - baseline) / steps

        model.zero_grad()
        scaled_input.grad = None
        del scaled_input, outputs, loss
        torch.cuda.empty_cache()

    del inputs
    # Detach integrated gradients and return
    return integrated_grads.detach()
    

def gradient_integrated(targets, lenghts, criterion, model_name, model, trial, patient, treshold_labels, ig_gradients):
    
    # label_names = ['General C.', 'Shoulder C.', 'Shoulder Elevation', 'Exaggerated Shoulder Abd.', 'Trunk C.', 'Head C.']
    label_names = ['General C']

    trial_1 =[0, 2]
    trial_batch = [[0, 15], [], [0]]

    for label in range(len(label_names)):
        
        slc = torch.relu(ig_gradients[label])
        # slc = slc[:, 0:lenghts[0], :]
        if model_name != 'LSTM':
            slc = smooth_gradients(slc, kernel_size=8)
        saliency = torch.nn.functional.interpolate(slc.unsqueeze(0), size=(slc.shape[1], 33), mode='nearest').squeeze(0)
        
        map = torch.zeros_like(saliency)
        
        for i in range(saliency.shape[0]):
            map[i] = (saliency[i] - saliency[i].min()) / (saliency[i].max() - saliency[i].min())
        
        # if patient in [3, 11, 17]  and trial in [0, 15, 65]:

        #     # if trial in trial_1:
                
        #         # for j in trial_batch[trial]:
        #         fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        #         axes = axes.flatten()

        #         fig2, axes2 = plt.subplots(2, 3, figsize=(15, 10))
        #         axes2 = axes2.flatten()
                
        #         active_labels = [label_names[i] for i in range(1, len(label_names)) if targets[0, i] > 0]
        #         if active_labels:
        #             active_labels_str = ", ".join(active_labels)
        #         else:
        #             active_labels_str = "No compensation"
                
        #         sns.heatmap(map[0][0:lenghts[0]].T.detach().cpu().numpy(), cmap='RdYlBu', ax=axes[label], cbar_kws={'label': 'Normalized Saliency'})
        #         axes[label].set_xlabel("Frames", fontsize=12)
        #         axes[label].set_ylabel("Joints", fontsize=12)
        #         axes[label].set_title(f"Label: {label_names[label]}", fontsize=14)
        #         axes[label].tick_params(axis='both', which='major', labelsize=10)
                
        #         head_joints = map[0][0:lenghts[0], :].sum(dim=1).detach().cpu().numpy()
        #         axes2[label].plot(head_joints)
        #         axes2[label].set_title(f"Label: {label_names[label]}", fontsize=14)
        #         axes2[label].set_xlabel("Frames", fontsize=12)
        #         axes2[label].set_ylabel("Sum of Saliency", fontsize=12)
                
        #         fig.suptitle(f"{model_name}: Saliency Maps of Patient {patient + 1}:  Trial {trial} \n Active Labels: {active_labels_str}", fontsize=16, weight='bold')
        #         fig.tight_layout(rect=[0, 0, 1, 0.96])
        #         fig.savefig(f"saliency_maps/integrated_gradients/{model_name}_patient_{patient}_trial_{trial}_IG.png", dpi=300)
        #         plt.close(fig)
                
        #         fig2.suptitle(f"{model_name}: Sum of Saliency for Patient {patient + 1}:  Trial {trial}", fontsize=16, weight='bold')
        #         fig2.tight_layout(rect=[0, 0, 1, 0.96])
        #         fig2.savefig(f"saliency_maps/integrated_gradients/{model_name}_patient_{patient}_trial_{trial}_sum_IG.png", dpi=300)
        #         plt.close(fig2)
                
        if label == 0:
            binary_map = (map[0][0:lenghts[0]].sum(dim=1) < treshold_labels).int().detach().cpu().numpy()
            # binary_map = []
            # for m in range(0, lenghts.shape[0]):
            #     binary_map.append((map[m][0:lenghts[m]].sum(dim=1) < treshold_labels).int().detach().cpu().numpy())

    return binary_map

def vanilla_gradients(test_loader, criterion, model_name, model, patient, device, treshold_labels):\

    model.eval()
    if model_name == 'LSTM':
        model.train()
    
    for batch_idx, (inputs, targets, lengths, inputs2) in enumerate(test_loader):
        
        inputs, targets = inputs.to(device, non_blocking=True).float(), targets.to(device, non_blocking=True).float()
        lengths = lengths.to('cpu')
        
        inputs.requires_grad = True
        
        if model_name == 'moment':
            vg = Saliency(model)
            vg_gradients = vg.attribute(inputs, baselines=inputs * 0, target=0)      

        else: 
            vg = Saliency(model)
            vg_gradients = vg.attribute(inputs, baselines=inputs * 0, target=0, additional_forward_args=lengths)

        slc = torch.relu(vg_gradients)
        
        if model_name != 'LSTM':
            slc = smooth_gradients(slc, kernel_size=8)
        saliency = torch.nn.functional.interpolate(slc.unsqueeze(0), size=(slc.shape[1], 33), mode='nearest').squeeze(0)
        
        map = torch.zeros_like(saliency)
        
        for i in range(saliency.shape[0]):
            map[i] = (saliency[i] - saliency[i].min()) / (saliency[i].max() - saliency[i].min())
        
        # still need to revise this for several batches
        binary_map = (map[0][0:lengths[0]].sum(dim=1) < treshold_labels).int().detach().cpu().numpy()
        
        torch.cuda.empty_cache()
        
    return binary_map



def smooth_gradients(grad, kernel_size=5):
    num_joints = grad.shape[2]
    
    # Create the smoothing kernel
    kernel = torch.ones((num_joints, 1, kernel_size), dtype=grad.dtype, device=grad.device) / kernel_size
    
    # Apply convolution to smooth the gradients
    smoothed_grad = torch.nn.functional.conv1d(
        grad.transpose(1, 2),  # Shape: (batch_size, num_joints, seq_length)
        kernel,
        padding=kernel_size // 2,
        groups=num_joints
    ).transpose(1, 2)  # Shape back to (batch_size, seq_length, num_joints)
    
    return smoothed_grad


def save_pseudo_labels(pseudo_labels, save_dir, model_name, patient, method):
    
    path = f'{save_dir}/{model_name}/{method}_{patient}'
    os.makedirs(path, exist_ok=True)
    for m, labels in enumerate(pseudo_labels):
        with open(os.path.join(path, f'pseudo_labels_{m}.pkl'), 'wb') as f:
            pickle.dump(labels, f)





def grad_cam_II(input, targets, outputs, output_dir, lengths, criterion, model_name, model, trial, patient):
    
    if patient == 0 and trial in [0, 15, 25, 35, 45, 55, 65]:

        label_names = ['General C.', 'Shoulder C.', 'Shoulder Elevation', 'Exaggerated Shoulder Abd.', 'Trunk C.', 'Head C.']
        
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        axes = axes.flatten()
        
        for label in range(len(label_names)):   
            
            model.zero_grad()
            
            loss = criterion(outputs[:, label], targets[:, label])
            loss.backward(retain_graph=True)
            
            activations = model.moment_model.activations
            gradients = model.moment_model.gradients 
            
            activations_mean = activations[2].mean(dim=1)  
            gradients = gradients.sum(dim=2)
            cls_token = activations_mean[:,0]

            weights_attention = cls_token * gradients

            interpolated_map = F.interpolate(
                weights_attention.unsqueeze(0).unsqueeze(0),  
                size=(33, 512),  # Target size
                mode="bilinear",
                align_corners=False
            ).squeeze(0).squeeze(0)  # Shape: [33, lengths]
            interpolated_map = torch.relu(interpolated_map)
            normalized_map = (interpolated_map - interpolated_map.min()) / (interpolated_map.max() - interpolated_map.min())

            normalized_map_np = normalized_map.cpu().numpy()

            sns.heatmap(normalized_map_np[:,:lengths[0]], cmap="viridis", cbar=True, ax=axes[label])
            axes[label].set_title(f"Label: {label_names[label]}")
            axes[label].set_xlabel("Sequence Lengths")
            axes[label].set_ylabel("Number of Joints")
        
        plt.tight_layout()
        plt.savefig(f'saliency_maps/grad_cam_II/grad-cam_II_patient_{patient}_trial_{trial}.png', dpi=300)
        plt.show()
        
    
    return 

def save_pseudo_labels(pseudo_labels, save_dir, model_name, patient, method):
    
    path = f'{save_dir}/{model_name}/{method}_{patient}'
    os.makedirs(path, exist_ok=True)
    for m, labels in enumerate(pseudo_labels):
        with open(os.path.join(path, f'pseudo_labels_{m}.pkl'), 'wb') as f:
            pickle.dump(labels, f)