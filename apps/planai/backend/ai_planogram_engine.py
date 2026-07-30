"""
PLONAGRAM AI ENGINE v3.0
Deep Reinforcement Learning Planogram Optimizer
Minimal POC → Production Ready

Architecture:
- State: Planogram representation as tensor
- Agent: DQN with experience replay
- Reward: Multi-objective scoring
- Training: Synthetic + Real data
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque, namedtuple
from typing import List, Dict, Tuple, Optional, Any
import json
from dataclasses import dataclass, asdict
from enum import Enum

# ==================== CONFIGURATION ====================

@dataclass
class EngineConfig:
    """Engine configuration"""
    max_shelves: int = 50
    max_width_cm: int = 200
    state_features: int = 12  # Occupancy, weight, category, brand, sales, etc.
    
    # RL parameters
    learning_rate: float = 0.0001
    gamma: float = 0.99  # Discount factor
    epsilon_start: float = 1.0
    epsilon_end: float = 0.01
    epsilon_decay: float = 0.995
    batch_size: int = 64
    memory_size: int = 100000
    target_update_freq: int = 1000
    
    # Reward weights
    sales_weight: float = 0.30
    ergonomic_weight: float = 0.20
    brand_cluster_weight: float = 0.15
    cross_sell_weight: float = 0.20
    space_efficiency_weight: float = 0.10
    constraint_penalty: float = 1000.0
    
    device: str = "cuda" if torch.cuda.is_available() else "cpu"


# ==================== DATA STRUCTURES ====================

class StorageType(Enum):
    AMBIENT = "AMBIENT"
    CHILLED = "CHILLED"
    FROZEN = "FROZEN"


@dataclass
class Product:
    sku: str
    name: str
    brand: str
    category_l1: str
    category_l2: str
    width_cm: float
    height_cm: float
    depth_cm: float
    weight_kg: float
    sales_7d: float
    storage_type: str
    case_pack: int = 1
    brand_id: int = 0
    category_id: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Shelf:
    shelf_id: int
    width_cm: float
    height_cm: float
    depth_cm: float
    storage_type: str
    position_y: float  # Height from ground (ergonomics)
    products: List[Dict] = None
    used_width_cm: float = 0.0
    used_weight_kg: float = 0.0
    
    def __post_init__(self):
        if self.products is None:
            self.products = []
    
    def remaining_width(self) -> float:
        return self.width_cm - self.used_width_cm
    
    def can_fit(self, product: Product, facing: int = 1) -> bool:
        required_width = product.width_cm * facing * 1.05  # 5% buffer
        return (required_width <= self.remaining_width() and
                product.height_cm <= self.height_cm and
                product.depth_cm <= self.depth_cm)


Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done'])


# ==================== STATE REPRESENTATION ====================

class PlanogramState:
    """
    State representation as 3D tensor: [shelves, width_bins, features]
    Features per bin:
        0: Occupancy (0/1)
        1: Weight (normalized)
        2: Category ID (one-hot encoded via embedding)
        3: Brand ID
        4: Sales score (normalized)
        5: Height utilization
        6: Storage type (0=ambient, 1=chilled, 2=frozen)
        7: Ergonomic score
        8-11: Reserved for future features
    """
    
    def __init__(self, shelves: List[Shelf], remaining_products: List[Product], config: EngineConfig):
        self.shelves = shelves
        self.remaining_products = remaining_products
        self.config = config
        self.width_bins = config.max_width_cm
    
    def to_tensor(self) -> torch.Tensor:
        """Convert state to tensor representation"""
        n_shelves = min(len(self.shelves), self.config.max_shelves)
        state = np.zeros((n_shelves, self.width_bins, self.config.state_features), dtype=np.float32)
        
        for shelf_idx, shelf in enumerate(self.shelves[:n_shelves]):
            for product_dict in shelf.products:
                pos = int(product_dict.get('position_cm', 0))
                width = int(product_dict.get('width_cm', 1))
                facing = product_dict.get('facing', 1)
                total_width = int(width * facing)
                
                if pos + total_width > self.width_bins:
                    continue
                
                # Fill features
                state[shelf_idx, pos:pos+total_width, 0] = 1  # Occupancy
                state[shelf_idx, pos:pos+total_width, 1] = product_dict.get('weight_kg', 0) / 10.0  # Normalized weight
                state[shelf_idx, pos:pos+total_width, 2] = product_dict.get('category_id', 0) / 100.0
                state[shelf_idx, pos:pos+total_width, 3] = product_dict.get('brand_id', 0) / 100.0
                state[shelf_idx, pos:pos+total_width, 4] = product_dict.get('sales_7d', 0) / 1000.0  # Normalized sales
                state[shelf_idx, pos:pos+total_width, 5] = product_dict.get('height_cm', 0) / shelf.height_cm
                
                # Storage type encoding
                storage_map = {'AMBIENT': 0, 'CHILLED': 0.5, 'FROZEN': 1.0}
                state[shelf_idx, pos:pos+total_width, 6] = storage_map.get(shelf.storage_type, 0)
                
                # Ergonomic score (based on shelf height)
                ergonomic = 1.0 - abs(shelf.position_y - 120) / 120.0  # Optimal at 120cm
                state[shelf_idx, pos:pos+total_width, 7] = max(0, ergonomic)
        
        return torch.FloatTensor(state)
    
    def get_valid_actions(self) -> List[Tuple[int, int, int]]:
        """
        Returns list of valid (shelf_idx, product_idx, facing) tuples
        """
        if not self.remaining_products:
            return []
        
        valid_actions = []
        
        for prod_idx, product in enumerate(self.remaining_products):
            for shelf_idx, shelf in enumerate(self.shelves):
                # Storage type must match
                if shelf.storage_type != product.storage_type:
                    continue
                
                # Try different facings
                for facing in [1, 2, 3, 4]:
                    if shelf.can_fit(product, facing):
                        valid_actions.append((shelf_idx, prod_idx, facing))
        
        return valid_actions
    
    def apply_action(self, action: Tuple[int, int, int]) -> 'PlanogramState':
        """Apply action and return new state"""
        shelf_idx, product_idx, facing = action
        
        if product_idx >= len(self.remaining_products):
            return self
        
        product = self.remaining_products[product_idx]
        shelf = self.shelves[shelf_idx]
        
        # Place product
        product_dict = {
            **product.to_dict(),
            'facing': facing,
            'position_cm': shelf.used_width_cm,
            'shelf_id': shelf.shelf_id,
        }
        
        shelf.products.append(product_dict)
        shelf.used_width_cm += product.width_cm * facing * 1.05
        shelf.used_weight_kg += product.weight_kg * facing
        
        # Create new state with product removed
        new_remaining = [p for i, p in enumerate(self.remaining_products) if i != product_idx]
        
        return PlanogramState(self.shelves, new_remaining, self.config)
    
    def is_terminal(self) -> bool:
        """Check if all products placed or no valid actions"""
        return len(self.remaining_products) == 0 or len(self.get_valid_actions()) == 0


# ==================== REWARD CALCULATION ====================

class RewardCalculator:
    """Multi-objective reward function"""
    
    def __init__(self, config: EngineConfig):
        self.config = config
    
    def calculate(self, state: PlanogramState, action: Tuple[int, int, int], 
                  next_state: PlanogramState) -> float:
        """Calculate reward for taking action in state"""
        shelf_idx, product_idx, facing = action
        
        if product_idx >= len(state.remaining_products):
            return -self.config.constraint_penalty
        
        product = state.remaining_products[product_idx]
        shelf = state.shelves[shelf_idx]
        
        reward = 0.0
        
        # 1. Sales potential reward
        sales_score = product.sales_7d / 100.0  # Normalize
        reward += sales_score * self.config.sales_weight * 100
        
        # 2. Ergonomic placement (eye-level is best)
        optimal_height = 120.0  # cm
        height_diff = abs(shelf.position_y - optimal_height)
        ergonomic_score = max(0, 1.0 - (height_diff / optimal_height))
        
        # High-sales products should be at eye level
        if product.sales_7d > 50:  # High velocity
            reward += ergonomic_score * self.config.ergonomic_weight * 100
        
        # 3. Brand clustering reward
        same_brand_nearby = sum(
            1 for p in shelf.products 
            if p.get('brand', '') == product.brand
        )
        reward += same_brand_nearby * 10 * self.config.brand_cluster_weight
        
        # 4. Category clustering
        same_category_nearby = sum(
            1 for p in shelf.products
            if p.get('category_l2', '') == product.category_l2
        )
        reward += same_category_nearby * 8 * self.config.brand_cluster_weight
        
        # 5. Cross-sell opportunity (simplified - same category different brand)
        cross_sell_potential = sum(
            1 for p in shelf.products
            if p.get('category_l2', '') == product.category_l2 and p.get('brand', '') != product.brand
        )
        reward += cross_sell_potential * 5 * self.config.cross_sell_weight
        
        # 6. Space efficiency
        space_utilization = shelf.used_width_cm / shelf.width_cm
        if 0.7 <= space_utilization <= 0.95:  # Sweet spot
            reward += 20 * self.config.space_efficiency_weight
        elif space_utilization > 0.95:
            reward -= 10  # Too tight, hard to restock
        
        # 7. Facing optimization (higher sales = more facings)
        optimal_facing = min(4, max(1, int(product.sales_7d / 20)))
        facing_diff = abs(facing - optimal_facing)
        reward -= facing_diff * 5
        
        # 8. Weight distribution (heavy items at bottom)
        if product.weight_kg > 2.0 and shelf.position_y > 100:
            reward -= 30  # Penalty for heavy items high up
        
        # 9. Storage type violation (hard constraint)
        if shelf.storage_type != product.storage_type:
            reward -= self.config.constraint_penalty
        
        # 10. Capacity violation
        if not shelf.can_fit(product, facing):
            reward -= self.config.constraint_penalty
        
        return reward


# ==================== NEURAL NETWORK ====================

class DQN(nn.Module):
    """Deep Q-Network for action-value estimation"""
    
    def __init__(self, config: EngineConfig):
        super(DQN, self).__init__()
        self.config = config
        
        # Convolutional layers to process shelf grid
        self.conv_layers = nn.Sequential(
            nn.Conv2d(config.state_features, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((10, 20))  # Reduce spatial dimensions
        )
        
        # Fully connected layers
        flattened_size = 128 * 10 * 20
        self.fc_layers = nn.Sequential(
            nn.Linear(flattened_size, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, 128),
            nn.ReLU(),
        )
        
        # Output: Q-value for current state
        self.value_head = nn.Linear(128, 1)
    
    def forward(self, state_tensor: torch.Tensor) -> torch.Tensor:
        """
        Forward pass
        state_tensor: [batch, shelves, width, features]
        Returns: [batch, 1] Q-value
        """
        # Transpose to [batch, features, shelves, width] for Conv2d
        x = state_tensor.permute(0, 3, 1, 2)
        
        # Convolutional layers
        x = self.conv_layers(x)
        
        # Flatten
        x = x.view(x.size(0), -1)
        
        # Fully connected
        x = self.fc_layers(x)
        
        # Value output
        value = self.value_head(x)
        
        return value


# ==================== RL AGENT ====================

class PlanogramRLAgent:
    """DQN Agent with experience replay"""
    
    def __init__(self, config: EngineConfig):
        self.config = config
        self.device = torch.device(config.device)
        
        # Q-networks
        self.policy_net = DQN(config).to(self.device)
        self.target_net = DQN(config).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        
        # Optimizer
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=config.learning_rate)
        
        # Replay memory
        self.memory = deque(maxlen=config.memory_size)
        
        # Training state
        self.epsilon = config.epsilon_start
        self.steps_done = 0
        self.reward_calculator = RewardCalculator(config)
    
    def select_action(self, state: PlanogramState) -> Optional[Tuple[int, int, int]]:
        """Epsilon-greedy action selection"""
        valid_actions = state.get_valid_actions()
        
        if not valid_actions:
            return None
        
        # Epsilon-greedy
        if random.random() < self.epsilon:
            return random.choice(valid_actions)
        
        # Greedy: evaluate all valid actions
        state_tensor = state.to_tensor().unsqueeze(0).to(self.device)
        
        best_action = None
        best_value = float('-inf')
        
        with torch.no_grad():
            for action in valid_actions:
                # Simulate action
                next_state = state.apply_action(action)
                next_tensor = next_state.to_tensor().unsqueeze(0).to(self.device)
                
                # Get Q-value
                q_value = self.policy_net(next_tensor).item()
                
                if q_value > best_value:
                    best_value = q_value
                    best_action = action
        
        return best_action
    
    def store_experience(self, state: PlanogramState, action: Tuple[int, int, int],
                        reward: float, next_state: PlanogramState, done: bool):
        """Store experience in replay buffer"""
        exp = Experience(
            state.to_tensor(),
            action,
            reward,
            next_state.to_tensor(),
            done
        )
        self.memory.append(exp)
    
    def train_step(self) -> Optional[float]:
        """Single training step on batch from memory"""
        if len(self.memory) < self.config.batch_size:
            return None
        
        # Sample batch
        batch = random.sample(self.memory, self.config.batch_size)
        
        # Unpack
        state_batch = torch.stack([exp.state for exp in batch]).to(self.device)
        reward_batch = torch.FloatTensor([exp.reward for exp in batch]).to(self.device)
        next_state_batch = torch.stack([exp.next_state for exp in batch]).to(self.device)
        done_batch = torch.FloatTensor([exp.done for exp in batch]).to(self.device)
        
        # Current Q-values
        current_q = self.policy_net(state_batch).squeeze()
        
        # Target Q-values
        with torch.no_grad():
            next_q = self.target_net(next_state_batch).squeeze()
            target_q = reward_batch + (1 - done_batch) * self.config.gamma * next_q
        
        # Loss
        loss = nn.MSELoss()(current_q, target_q)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()
        
        # Decay epsilon
        self.epsilon = max(
            self.config.epsilon_end,
            self.epsilon * self.config.epsilon_decay
        )
        
        # Update target network
        self.steps_done += 1
        if self.steps_done % self.config.target_update_freq == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
        
        return loss.item()
    
    def optimize_planogram(self, products: List[Product], shelves: List[Shelf],
                          max_steps: int = 500) -> Tuple[List[Shelf], List[Product], List[float]]:
        """
        Optimize planogram placement
        Returns: (shelves_with_products, unplaced_products, reward_history)
        """
        state = PlanogramState(shelves, products, self.config)
        reward_history = []
        
        for step in range(max_steps):
            if state.is_terminal():
                break
            
            # Select action
            action = self.select_action(state)
            if action is None:
                break
            
            # Apply action
            next_state = state.apply_action(action)
            
            # Calculate reward
            reward = self.reward_calculator.calculate(state, action, next_state)
            reward_history.append(reward)
            
            # Store experience
            done = next_state.is_terminal()
            self.store_experience(state, action, reward, next_state, done)
            
            # Train
            loss = self.train_step()
            
            # Move to next state
            state = next_state
        
        return state.shelves, state.remaining_products, reward_history
    
    def save_model(self, path: str):
        """Save model checkpoint"""
        torch.save({
            'policy_net': self.policy_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'steps_done': self.steps_done,
        }, path)
    
    def load_model(self, path: str):
        """Load model checkpoint"""
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint['policy_net'])
        self.target_net.load_state_dict(checkpoint['target_net'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint['epsilon']
        self.steps_done = checkpoint['steps_done']


# ==================== SYNTHETIC DATA GENERATION ====================

def generate_synthetic_products(n_products: int = 50) -> List[Product]:
    """Generate synthetic products for testing"""
    brands = ['Ülker', 'Eti', 'Nestle', 'Coca Cola', 'Pınar', 'Sütaş', 'Algida']
    categories_l1 = ['Gıda', 'İçecek', 'Temizlik', 'Kişisel Bakım']
    categories_l2 = ['Çikolata', 'Bisküvi', 'Süt', 'Meşrubat', 'Deterjan', 'Sabun']
    storage_types = ['AMBIENT', 'CHILLED', 'FROZEN']
    
    products = []
    for i in range(n_products):
        products.append(Product(
            sku=f'SKU{i:04d}',
            name=f'Product {i}',
            brand=random.choice(brands),
            category_l1=random.choice(categories_l1),
            category_l2=random.choice(categories_l2),
            width_cm=random.uniform(5, 30),
            height_cm=random.uniform(10, 40),
            depth_cm=random.uniform(10, 30),
            weight_kg=random.uniform(0.1, 5.0),
            sales_7d=random.uniform(1, 200),
            storage_type=random.choice(storage_types),
            case_pack=random.randint(1, 12),
            brand_id=hash(random.choice(brands)) % 100,
            category_id=hash(random.choice(categories_l2)) % 100,
        ))
    
    return products


def generate_synthetic_shelves(n_shelves: int = 20) -> List[Shelf]:
    """Generate synthetic shelf layout"""
    storage_types = ['AMBIENT', 'CHILLED', 'FROZEN']
    
    shelves = []
    for i in range(n_shelves):
        shelves.append(Shelf(
            shelf_id=i,
            width_cm=200.0,
            height_cm=random.uniform(30, 50),
            depth_cm=50.0,
            storage_type=random.choice(storage_types),
            position_y=random.uniform(20, 200),  # Height from ground
        ))
    
    return shelves


# ==================== MAIN ENGINE ====================

class PlanogramAIEngine:
    """Main AI Engine interface"""
    
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self.agent = PlanogramRLAgent(self.config)
    
    def optimize(self, products: List[Product], shelves: List[Shelf]) -> Dict[str, Any]:
        """
        Main optimization entry point
        Returns complete result with diagnostics
        """
        # Run optimization
        optimized_shelves, unplaced, reward_history = self.agent.optimize_planogram(
            products, shelves
        )
        
        # Calculate metrics
        total_placed = len(products) - len(unplaced)
        total_capacity = sum(s.width_cm for s in shelves)
        used_capacity = sum(s.used_width_cm for s in optimized_shelves)
        
        result = {
            'planogram': {
                'shelves': [
                    {
                        'shelf_id': s.shelf_id,
                        'width_cm': s.width_cm,
                        'height_cm': s.height_cm,
                        'storage_type': s.storage_type,
                        'position_y': s.position_y,
                        'used_width_cm': s.used_width_cm,
                        'used_weight_kg': s.used_weight_kg,
                        'products': s.products
                    }
                    for s in optimized_shelves
                ]
            },
            'summary': {
                'total_products': len(products),
                'placed_products': total_placed,
                'unplaced_products': len(unplaced),
                'placement_rate': round(total_placed / len(products) * 100, 2),
                'capacity_utilization': round(used_capacity / total_capacity * 100, 2),
                'avg_reward': round(np.mean(reward_history), 2) if reward_history else 0,
                'total_reward': round(sum(reward_history), 2),
            },
            'unplaced': [p.to_dict() for p in unplaced],
            'diagnostics': {
                'reward_history': reward_history,
                'epsilon': self.agent.epsilon,
                'training_steps': self.agent.steps_done,
                'memory_size': len(self.agent.memory),
            },
            'engine_version': 'PLONAGRAM_AI_ENGINE_v3.0_RL',
        }
        
        return result
    
    def train_episode(self, n_episodes: int = 100):
        """Training loop on synthetic data"""
        print(f"Training {n_episodes} episodes on synthetic data...")
        
        episode_rewards = []
        
        for episode in range(n_episodes):
            products = generate_synthetic_products(50)
            shelves = generate_synthetic_shelves(20)
            
            result = self.optimize(products, shelves)
            total_reward = result['summary']['total_reward']
            placement_rate = result['summary']['placement_rate']
            
            episode_rewards.append(total_reward)
            
            if (episode + 1) % 10 == 0:
                avg_reward = np.mean(episode_rewards[-10:])
                print(f"Episode {episode+1}/{n_episodes} | "
                      f"Avg Reward: {avg_reward:.2f} | "
                      f"Placement: {placement_rate:.1f}% | "
                      f"Epsilon: {self.agent.epsilon:.3f}")
        
        print(f"\nTraining complete!")
        print(f"Final avg reward (last 10): {np.mean(episode_rewards[-10:]):.2f}")
        
        return episode_rewards
    
    def save(self, path: str):
        """Save trained model"""
        self.agent.save_model(path)
        print(f"Model saved to {path}")
    
    def load(self, path: str):
        """Load trained model"""
        self.agent.load_model(path)
        print(f"Model loaded from {path}")


# ==================== EXAMPLE USAGE ====================

if __name__ == "__main__":
    print("=" * 60)
    print("PLONAGRAM AI ENGINE v3.0 - Minimal POC")
    print("Deep Reinforcement Learning Planogram Optimizer")
    print("=" * 60)
    
    # Initialize engine
    config = EngineConfig()
    engine = PlanogramAIEngine(config)
    
    print(f"\nDevice: {config.device}")
    print(f"State features: {config.state_features}")
    print(f"Memory size: {config.memory_size}")
    
    # Train on synthetic data
    print("\n" + "=" * 60)
    print("TRAINING PHASE")
    print("=" * 60)
    rewards = engine.train_episode(n_episodes=50)
    
    # Save model
    engine.save('planogram_ai_model.pt')
    
    # Test on new data
    print("\n" + "=" * 60)
    print("TESTING PHASE")
    print("=" * 60)
    
    test_products = generate_synthetic_products(30)
    test_shelves = generate_synthetic_shelves(15)
    
    print(f"\nOptimizing {len(test_products)} products on {len(test_shelves)} shelves...")
    result = engine.optimize(test_products, test_shelves)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(json.dumps(result['summary'], indent=2))
    
    print(f"\nUnplaced products: {len(result['unplaced'])}")
    if result['unplaced']:
        print("Sample unplaced:")
        for p in result['unplaced'][:3]:
            print(f"  - {p['sku']}: {p['name']} ({p['storage_type']})")
    
    print("\n✓ POC Complete!")
