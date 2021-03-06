

import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt 
matplotlib.style.use('ggplot')
from torchnet import meter

import pickle as pkl 
from custom_model import *
from loaders import *
import time


import torch 
from torch.autograd import Variable
from torch.utils.data import Dataset, DataLoader
import torch.optim as optim
from torch import nn
from torchvision import transforms
from sklearn.decomposition import PCA 
from torchvision import transforms 
from sklearn.model_selection import KFold

tran = transforms.Compose([transforms.ToTensor()])
#sET NUMBER OF FOLDS FOR CROSS-VALIDATION
folds = 4

def preprocess(df):
    df['bare_nuclei'].replace({'?': np.nan}, inplace = True)
    df.dropna(inplace=True)
    df["bare_nuclei"] = df["bare_nuclei"].astype(int)
    df.drop(["id"], axis = 1, inplace=True)
    df["class"] = df["class"].map({2:0, 4:1})
    return df



load = loaders("data/data.csv", preprocess)



a = open("data/datasets", "rb")
datasets = pkl.load(a)


drop_cols = ["marg_adhesion", "single_epith_cell_size", "mitoses"]

         
for x in datasets:
    x.drop(drop_cols, axis = 1, inplace = True)


datasets = [pca_dataframe(x,2).iloc[:,:] for x in datasets]



train_valid_data = pd.concat(datasets[0:2])

tran = transforms.Compose([transforms.ToTensor()])

comb_data = pd.concat(datasets)


D_in, H, D_out = datasets[0].shape[1] - 1, 30, 2
 
model = torch.nn.Sequential(
    torch.nn.Linear(D_in, H),
    torch.nn.Tanh(),
    torch.nn.Linear(H, D_out),
    torch.nn.Softmax()
)

lr = 0.1
loss_fn = nn.CrossEntropyLoss()
wd = 0.1
optimizer = optim.Adam(model.parameters(), lr, weight_decay=wd)

def init_weights(m):
    if type(m) == nn.Linear:
        m.weight.data.normal_(0, 2/float(12))
        m.bias.data.normal_(0, 2/float(12))

kf = KFold(folds)

cross_val_accu = []
cross_val_models = []
best_accuracy = 0
best_accuracy_model = None

 
print("LR:", lr, "WD:", wd)
for tr, te in kf.split(train_valid_data):
    
    train = train_valid_data.iloc[tr,:]   #define the training set
    valid = train_valid_data.iloc[te,:] #define the set of test as well as validation
    datasets = [train, valid, valid]
    trainloader, testloader, validloader = get_dataloaders(datasets, tran, batch_size = 30)
    a = custom_model(model, loss_fn)
    a.model.apply(init_weights)
    a.train(trainloader, testloader, validloader, optimizer, 30, plot = True)
    cross_val_models.append(a.model.state_dict())
    accuracy, ct, auc, cm = a.metrics_val(testloader)
    if accuracy > best_accuracy:
        best_accuracy_model = a.model.state_dict()
        best_accuracy = accuracy
    cross_val_accu.append(accuracy)
    print ("Accuracy:", accuracy, ct)




print ("Average Accuracy:", sum(cross_val_accu)/len(cross_val_accu))

#cross_val_models = pkl.load(open("cross_models_best", "rb"))
am = meter.AUCMeter()
cm = meter.ConfusionMeter(2)
correct = 0
total = 0
Y_ = []
a = custom_model(model, loss_fn)
for data in testloader:   
    Y_ = []
    x,y = data
#    a.model.load_state_dict(cross_val_models)
#    y_ = a.model(Variable(x))
    for mod in cross_val_models:
        a.model.load_state_dict(mod)
        Y_.append(a.model(Variable(x)))
    
    y_ = Y_[0]
    _, predicted = torch.max(y_.data, 1)
    
    
    cm.add(y_.data, y)
    
    am.add(y_.data[:,1].clone(),y)
    total += y.size(0)
    correct += (predicted == y).sum()

print (correct, total)


combset = WBCDataset(comb_data, tran)
combloader = DataLoader(combset, shuffle= True, batch_size=30, num_workers=4)


am = meter.AUCMeter()
cm = meter.ConfusionMeter(2)
correct = 0
total = 0
Y_ = []
a = custom_model(model, loss_fn)
for data in combloader:   
    Y_ = []
    x,y = data
    for mod in cross_val_models:
        a.model.load_state_dict(mod)
        Y_.append(a.model(Variable(x)))
    
    y_ = Y_[0]
    _, predicted = torch.max(y_.data, 1)
    
    
    cm.add(y_.data, y)
    
    am.add(y_.data[:,1].clone(),y)
    total += y.size(0)
    correct += (predicted == y).sum()

print (correct, total)

print("Accuracy for the model is", round(correct/float(total)*100, 4), correct, "/", total)

print("Area under ROC curve for the given model is", round(am.value()[0],4))

print ("Confusion Matrix for the given model is\n", cm.value())

    
def decision_boundary_2d(models, df, f1, f2, label = "class", h = 0.2):
        """
        Renders a 2-dimensional decision boundary generated by
        the Neural Network for given data.
        
        df: Dataframe containing the data with labels as well as 
            the class. 
        
        xx: Column name of the feature to be plotted on the x-axis
        yy: Column name of the label to be plotted on the y-axis
        label: name of the column containing the class
        
        Returns: Plots the decision boundary with the points colored
                 with class
        """
        
        color = {1: "red", 0: "blue"}
        
        x = df[f1]
        y = df[f2]
        x_min, x_max = x.min() - 1, x.max() + 1
        y_min, y_max = y.min() - 1, y.max() + 1
        xx, yy = np.meshgrid(np.arange(x_min, x_max, h),
                         np.arange(y_min, y_max, h))
        
        grid = np.c_[xx.ravel(), yy.ravel()] 
        grid_tensor = Variable(torch.Tensor(grid))
        a = custom_model(model, loss_fn)
        Y_ = []
        for mod in models:
            a.model.load_state_dict(mod)
            Y_.append(a.model(grid_tensor).data)
        y_ = sum(Y_)/len(Y_)

        results = torch.max(y_, 1)[1].numpy()
        plt.contourf(xx, yy, results.reshape(xx.shape), cmap=plt.cm.coolwarm, alpha=0.8)
        plt.scatter(df[f1], df[f2], c=df[label].apply(lambda x: color[x]))
        
     
decision_boundary_2d(cross_val_models, comb_data, "PCA0", "PCA1")





