import torch
import numpy as np  
import torch.nn as nn
import torch.nn.utils as utils
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from visualization import gradient_normal, grad_cam, grad_cam_II, attention_weights, gradient_integrated, gradient_normal_II
from captum.attr import IntegratedGradients
from captum.attr import LayerGradCam
from captum.attr import Saliency, DeepLift, ShapleyValueSampling,GradientShap, LayerIntegratedGradients


def training(model, dataloader, optimizer, criterion, device, save_dir, model_name, thresholds, clip_value, optuna, epoch, scaler):
    
    model.train()
    running_loss = 0.0
    all_targets, all_sigmoid_outputs, all_predictions = [], [], []
    thresholds = torch.tensor(thresholds, device=device)
    
    if epoch == 0 and model_name in ['moment', 'AcT', 'SkateFormer', 'moment+dino']:
        
        if model_name == 'moment+dino':
            for name, param in model.named_parameters():
                if any(substring in name for substring in ["dinov2.encoder.layer.7", "moment_model.encoder.block.7"]):
                    param.requires_grad = True
                    print('Unfreez Layers:' ,name)
        else:
            for param in model.parameters():
                param.requires_grad = True
                
        print("All layers unfrozen!")
    
    for batch_idx, (inputs, targets, lengths, inputs2) in enumerate(dataloader):
        
        inputs, targets = inputs.to(device, non_blocking=True).float(), targets.to(device,non_blocking=True ).float()
        lengths = lengths.to('cpu')
        
        optimizer.zero_grad()

        # with torch.amp.autocast(device_type='cuda'):

        if model_name == 'moment':  
            outputs = model(inputs)
            
        elif model_name == 'moment+dino':
            inputs2 = inputs2.to(device, non_blocking=True).float()
            outputs = model(inputs, inputs2)
            
        else:
            outputs = model(inputs, lengths)
        
        loss = criterion(outputs, targets)
        # scaler.scale(loss).backward()
        loss.backward()
        
        if clip_value is not None:
            utils.clip_grad_value_(model.parameters(), clip_value)
                            
        # scaler.step(optimizer)
        # scaler.update()   
        optimizer.step()
        running_loss += loss.item()
        
        sigmoid_outputs = torch.sigmoid(outputs) 
        predicted = sigmoid_outputs > thresholds
        all_sigmoid_outputs.append(sigmoid_outputs.detach().cpu().numpy())
        all_targets.append(targets.cpu().detach().numpy())
        all_predictions.append(predicted.cpu().detach().numpy())
    
    if optuna:
        return running_loss / len(dataloader)
    
    all_targets = np.concatenate(all_targets, axis=0)
    all_predictions = np.concatenate(all_predictions, axis=0)
    all_sigmoid_outputs = np.concatenate(all_sigmoid_outputs, axis=0) 
    
    # metrics(all_targets, all_predictions, "train", save_dir, model_name)

    return running_loss / len(dataloader), all_targets, all_sigmoid_outputs



def validate(model, val_loader, criterion, device, mode, save_dir, model_name, thresholds, optuna, saliency_map, scaler, patient, treshold_labels, method):
    
    model.eval()
    if saliency_map and mode == 'testing' and model_name == 'LSTM':
        model.train()
    pseudo_labels = []
    val_loss = 0.0
    all_targets, all_predictions, all_sigmoid_outputs = [], [], []
    thresholds = torch.tensor(thresholds)
    
    if not saliency_map and mode =='testing':
        context_manager = torch.no_grad()
    else:
        context_manager = torch.enable_grad()

    with context_manager:
    
        for batch_idx, (inputs, targets, lengths, inputs2) in enumerate(val_loader):
            
            inputs, targets = inputs.to(device, non_blocking=True).float(), targets.to(device, non_blocking=True).float()
            
            if saliency_map and mode =='testing':
                inputs.requires_grad = True
            
            if model_name == 'moment':
                outputs = model(inputs)
            elif model_name == 'moment+dino':
                inputs2 = inputs2.to(device, non_blocking=True).float()
                outputs = model(inputs, inputs2)
            else: 
                outputs = model(inputs, lengths)
                
            loss = criterion(outputs, targets)
            val_loss += loss.item()
            
            sigmoid_outputs = torch.sigmoid(outputs) 
            predicted = sigmoid_outputs > thresholds.to(inputs.device)
            
            all_sigmoid_outputs.append(sigmoid_outputs.detach().cpu().numpy())
            all_targets.append(targets.cpu().numpy())
            all_predictions.append(predicted.cpu().numpy())
            
            
            if saliency_map and mode == 'testing':
                if method == 'ig':
                    num_labels = targets.shape[1]
                    attributions = []
                    ig = IntegratedGradients(model)

                    for label_idx in range(num_labels):
                        
                        attributions.append(ig.attribute(inputs, baselines=inputs * 0, target=label_idx))
                        # attributions.append(integrated_gradients(inputs, model, label_idx, baseline=None, steps=50))
                    pseudo_labels.append(gradient_integrated( targets, lengths, criterion, model_name, model, batch_idx, patient, treshold_labels, attributions))
                    
                if method == 'vg':
                    pseudo_labels.append(gradient_normal(inputs, targets, outputs, save_dir, lengths, criterion, model_name, model, batch_idx, patient, treshold_labels))
                    
                if method == 'grad_cam':
                    grad_cam(inputs, targets, outputs, save_dir, lengths, criterion, model_name, model, batch_idx, patient)
                                
    
    if saliency_map and mode == 'testing':
        return pseudo_labels
        
    val_loss /= len(val_loader)
    all_targets = np.concatenate(all_targets, axis=0)
    all_predictions = np.concatenate(all_predictions, axis=0)
    all_sigmoid_outputs = np.concatenate(all_sigmoid_outputs, axis=0)
    
    if optuna:
        
        return val_loss, f1_score(all_targets, all_predictions, average='samples', zero_division=0)
    
    # _ = metrics(all_targets, all_predictions, mode, save_dir, model_name)
    
    return val_loss, all_targets, all_predictions, all_sigmoid_outputs



def integrated_gradients(inputs, model, target_label_idx, baseline=None, steps=50):
    if baseline is None:
        baseline = torch.zeros_like(inputs).to(inputs.device)
    
    # Scale inputs and compute gradients
    scaled_inputs = [baseline + (float(i) / steps) * (inputs - baseline) for i in range(0, steps + 1)]
    grads = []
    
    for scaled_input in scaled_inputs:
        scaled_input.requires_grad = True
        outputs = model(scaled_input)
        loss = outputs[0, target_label_idx]
        loss.backward(retain_graph=True)
        grads.append(scaled_input.grad)
        model.zero_grad()
    
    # Average gradients and compute integrated gradients
    avg_grads = torch.mean(torch.stack(grads), dim=0)
    integrated_grads = (inputs - baseline) * avg_grads
    
    return integrated_grads